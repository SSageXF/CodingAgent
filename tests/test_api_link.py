from __future__ import annotations

import httpx
import pytest

from evidencecoder.api_link import APILink, APIAuthenticationError, ModelToolCall


def test_api_link_retries_and_parses_tool_calls():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, request=request, text="temporary")
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "inspect_tree",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    link = APILink(
        base_url="https://example.test/v1",
        model="fake",
        client=client,
        max_retries=2,
        sleep=lambda _: None,
    )
    reply = link.complete([{"role": "user", "content": "x"}], [])
    assert attempts == 2
    assert reply.tool_calls == (ModelToolCall("call-1", "inspect_tree", "{}"),)
    assert reply.prompt_tokens == 10


def test_api_link_does_not_retry_authentication_error():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, request=request)

    link = APILink(
        base_url="https://example.test/v1",
        model="fake",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=3,
    )
    with pytest.raises(APIAuthenticationError):
        link.complete([], [])
    assert attempts == 1
