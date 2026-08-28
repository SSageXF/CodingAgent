"""Runtime configuration loaded from explicit values and environment variables."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """All limits that affect one EvidenceCoder run.

    The model name intentionally has no default. OpenAI-compatible gateways use
    different names, and silently choosing one would make runs hard to reproduce.
    """

    workspace: Path
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    request_timeout_seconds: float = 120.0
    api_max_retries: int = 3
    max_cycles: int = 30
    wall_time_seconds: int = 1_200
    command_timeout_seconds: int = 60
    context_soft_limit_tokens: int = 60_000
    context_keep_cycles: int = 4
    max_consecutive_tool_errors: int = 5
    max_repeated_operation: int = 3
    auto_approve_writes: bool = False
    auto_approve_commands: bool = False
    save_run_log: bool = True

    @classmethod
    def from_env(cls, workspace: Path | str = ".", **overrides: object) -> "Settings":
        model = str(overrides.pop("model", "") or os.getenv("EVIDENCECODER_MODEL", "")).strip()
        base_url = str(
            overrides.pop("base_url", "")
            or os.getenv("EVIDENCECODER_BASE_URL", "https://api.openai.com/v1")
        ).strip()
        api_key = str(
            overrides.pop("api_key", "")
            or os.getenv("EVIDENCECODER_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
        ).strip()
        settings = cls(
            workspace=Path(workspace).expanduser().resolve(),
            model=model,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            request_timeout_seconds=_env_float(
                "EVIDENCECODER_REQUEST_TIMEOUT", 120.0, minimum=1.0, maximum=600.0
            ),
            api_max_retries=_env_int("EVIDENCECODER_API_RETRIES", 3, minimum=0, maximum=10),
            max_cycles=_env_int("EVIDENCECODER_MAX_CYCLES", 30, minimum=1, maximum=200),
            wall_time_seconds=_env_int(
                "EVIDENCECODER_WALL_TIME", 1_200, minimum=10, maximum=86_400
            ),
            command_timeout_seconds=_env_int(
                "EVIDENCECODER_COMMAND_TIMEOUT", 60, minimum=1, maximum=600
            ),
            context_soft_limit_tokens=_env_int(
                "EVIDENCECODER_CONTEXT_LIMIT", 60_000, minimum=2_000, maximum=1_000_000
            ),
            context_keep_cycles=_env_int(
                "EVIDENCECODER_CONTEXT_KEEP_CYCLES", 4, minimum=1, maximum=20
            ),
            max_consecutive_tool_errors=_env_int(
                "EVIDENCECODER_MAX_TOOL_ERRORS", 5, minimum=1, maximum=50
            ),
            max_repeated_operation=_env_int(
                "EVIDENCECODER_MAX_REPEATS", 3, minimum=2, maximum=20
            ),
        )
        if overrides:
            unknown = ", ".join(sorted(overrides))
            raise TypeError(f"unknown Settings overrides: {unknown}")
        return settings

    def with_overrides(self, **changes: object) -> "Settings":
        return replace(self, **changes)

    def validate(self) -> None:
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a directory: {self.workspace}")
        if not self.model:
            raise ValueError("model is required; use --model or EVIDENCECODER_MODEL")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if not 1 <= self.max_cycles <= 200:
            raise ValueError("max_cycles must be between 1 and 200")
        if not 10 <= self.wall_time_seconds <= 86_400:
            raise ValueError("wall_time_seconds must be between 10 and 86400")
