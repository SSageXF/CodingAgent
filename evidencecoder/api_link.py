"""A small OpenAI-compatible Chat Completions client.

This module deliberately implements only the transport needed by EvidenceCoder.
It does not use an agent SDK and it does not execute hosted tools.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Protocol, Sequence

import httpx


class APIError(RuntimeError):
    """Base class for model API failures."""


class APIAuthenticationError(APIError):
    """The gateway rejected the configured credentials."""


class APIProtocolError(APIError):
    """The gateway returned a response EvidenceCoder cannot interpret."""


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ModelReply:
    content: str
    tool_calls: tuple[ModelToolCall, ...] = ()
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ModelGateway(Protocol):
    def complete(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> ModelReply: ...


class APILink:
    """Synchronous, retrying client for `/chat/completions`."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: float = 120.0,
        max_retries: int = 3,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "APILink":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def complete(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> ModelReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise APIError(f"model API request failed after retries: {exc}") from exc
                self._sleep(min(2**attempt, 8))
                continue

            if response.status_code in {401, 403}:
                raise APIAuthenticationError(
                    f"model API authentication failed with HTTP {response.status_code}"
                )
            if response.status_code == 429 or response.status_code >= 500:
                last_error = APIError(f"retryable model API status: HTTP {response.status_code}")
                if attempt >= self.max_retries:
                    raise last_error
                self._sleep(min(2**attempt, 8))
                continue
            if response.is_error:
                detail = response.text[:500]
                raise APIError(f"model API returned HTTP {response.status_code}: {detail}")
            return self._parse_response(response)

        raise APIError(f"model API request failed: {last_error}")

    @staticmethod
    def _parse_response(response: httpx.Response) -> ModelReply:
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise APIProtocolError("response is missing choices[0].message") from exc

        raw_content = message.get("content")
        if raw_content is None:
            content = ""
        elif isinstance(raw_content, str):
            content = raw_content
        else:
            content = json.dumps(raw_content, ensure_ascii=False)

        parsed_calls: list[ModelToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            try:
                function = raw_call["function"]
                call_id = str(raw_call["id"])
                name = str(function["name"])
                arguments = function.get("arguments", "{}")
            except (KeyError, TypeError) as exc:
                raise APIProtocolError("tool call is missing id or function fields") from exc
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            if not call_id or not name:
                raise APIProtocolError("tool call id and name must be non-empty")
            parsed_calls.append(ModelToolCall(call_id, name, arguments))

        usage = data.get("usage") or {}
        return ModelReply(
            content=content,
            tool_calls=tuple(parsed_calls),
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
        )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
