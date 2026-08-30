"""Runtime configuration loaded from CLI values, the environment, and .env."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import re
from typing import Mapping


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _config_value(name: str, dotenv: Mapping[str, str]) -> str | None:
    environment_value = os.getenv(name)
    if environment_value is not None and environment_value.strip():
        return environment_value
    return dotenv.get(name)


def _env_int(
    name: str,
    default: int,
    dotenv: Mapping[str, str],
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = _config_value(name, dotenv)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_float(
    name: str,
    default: float,
    dotenv: Mapping[str, str],
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = _config_value(name, dotenv)
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
    def from_env(
        cls,
        workspace: Path | str = ".",
        *,
        env_file: Path | str = ".env",
        **overrides: object,
    ) -> "Settings":
        dotenv = _load_dotenv(env_file)
        model = str(
            overrides.pop("model", "") or _config_value("EVIDENCECODER_MODEL", dotenv) or ""
        ).strip()
        base_url = str(
            overrides.pop("base_url", "")
            or _config_value("EVIDENCECODER_BASE_URL", dotenv)
            or "https://api.openai.com/v1"
        ).strip()
        api_key = str(
            overrides.pop("api_key", "")
            or os.getenv("EVIDENCECODER_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
            or dotenv.get("EVIDENCECODER_API_KEY", "")
            or dotenv.get("OPENAI_API_KEY", "")
        ).strip()
        settings = cls(
            workspace=Path(workspace).expanduser().resolve(),
            model=model,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            request_timeout_seconds=_env_float(
                "EVIDENCECODER_REQUEST_TIMEOUT",
                120.0,
                dotenv,
                minimum=1.0,
                maximum=600.0,
            ),
            api_max_retries=_env_int(
                "EVIDENCECODER_API_RETRIES", 3, dotenv, minimum=0, maximum=10
            ),
            max_cycles=_env_int(
                "EVIDENCECODER_MAX_CYCLES", 30, dotenv, minimum=1, maximum=200
            ),
            wall_time_seconds=_env_int(
                "EVIDENCECODER_WALL_TIME", 1_200, dotenv, minimum=10, maximum=86_400
            ),
            command_timeout_seconds=_env_int(
                "EVIDENCECODER_COMMAND_TIMEOUT", 60, dotenv, minimum=1, maximum=600
            ),
            context_soft_limit_tokens=_env_int(
                "EVIDENCECODER_CONTEXT_LIMIT",
                60_000,
                dotenv,
                minimum=2_000,
                maximum=1_000_000,
            ),
            context_keep_cycles=_env_int(
                "EVIDENCECODER_CONTEXT_KEEP_CYCLES", 4, dotenv, minimum=1, maximum=20
            ),
            max_consecutive_tool_errors=_env_int(
                "EVIDENCECODER_MAX_TOOL_ERRORS", 5, dotenv, minimum=1, maximum=50
            ),
            max_repeated_operation=_env_int(
                "EVIDENCECODER_MAX_REPEATS", 3, dotenv, minimum=2, maximum=20
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
            raise ValueError("model is required; use --model, .env, or EVIDENCECODER_MODEL")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if not 1 <= self.max_cycles <= 200:
            raise ValueError("max_cycles must be between 1 and 200")
        if not 10 <= self.wall_time_seconds <= 86_400:
            raise ValueError("wall_time_seconds must be between 10 and 86400")


def _load_dotenv(path: Path | str) -> dict[str, str]:
    """Parse the small KEY=VALUE subset documented by .env.example."""

    source = Path(path).expanduser()
    if not source.is_file():
        return {}
    try:
        lines = source.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read .env file: {source}") from exc

    values: dict[str, str] = {}
    for line_number, original in enumerate(lines, start=1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, raw_value = line.partition("=")
        name = name.strip()
        if not separator or not _ENV_NAME.fullmatch(name):
            raise ValueError(f"invalid .env syntax at line {line_number}")
        values[name] = _parse_dotenv_value(raw_value.strip(), line_number)
    return values


def _parse_dotenv_value(value: str, line_number: int) -> str:
    if not value:
        return ""
    if value[0] in {'"', "'"}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise ValueError(f"unterminated quoted .env value at line {line_number}")
        inner = value[1:-1]
        if quote == '"':
            escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"'}
            return re.sub(r'\\([nrt\\"])', lambda match: escapes[match.group(1)], inner)
        return inner
    comment = re.search(r"\s+#", value)
    if comment:
        value = value[: comment.start()]
    return value.rstrip()
