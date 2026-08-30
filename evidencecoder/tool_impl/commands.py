"""Independent local command execution with bounded output and time."""

from __future__ import annotations

import os
import locale
from pathlib import Path
import signal
import subprocess
import time
from typing import Any

from ..runbook import OperationStatus, ToolOutcome


class LocalCommands:
    MAX_OUTPUT_CHARS = 12_000
    MAX_TIMEOUT_SECONDS = 300

    def __init__(self, root: Path | str, default_timeout_seconds: int = 60) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.default_timeout_seconds = min(
            max(1, int(default_timeout_seconds)), self.MAX_TIMEOUT_SECONDS
        )

    def run_local(self, arguments: dict[str, Any]) -> ToolOutcome:
        command = arguments["command"].strip()
        if not command:
            raise ValueError("command must not be empty")
        timeout = arguments.get("timeout_seconds", self.default_timeout_seconds)
        timeout = min(max(1, timeout), self.MAX_TIMEOUT_SECONDS)
        started = time.monotonic()
        popen_kwargs: dict[str, Any] = {
            "args": command,
            "shell": True,
            "cwd": self.root,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(**popen_kwargs)
        timed_out = False
        try:
            output_bytes, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            output_bytes, _ = process.communicate()
        duration_ms = int((time.monotonic() - started) * 1_000)
        output, output_encoding, decode_replacements = _decode_output(output_bytes or b"")
        rendered, truncated = _truncate_middle(output, self.MAX_OUTPUT_CHARS)
        if timed_out:
            return ToolOutcome(
                OperationStatus.TIMEOUT,
                f"command timed out after {timeout}s\n{rendered}",
                {
                    "command": command,
                    "timeout_seconds": timeout,
                    "exit_code": process.returncode,
                    "duration_ms": duration_ms,
                    "output_truncated": truncated,
                    "output_encoding": output_encoding,
                    "decode_replacements": decode_replacements,
                },
            )
        prefix = f"exit code: {process.returncode}"
        summary = prefix if not rendered else f"{prefix}\n{rendered}"
        return ToolOutcome(
            OperationStatus.OK,
            summary,
            {
                "command": command,
                "exit_code": process.returncode,
                "duration_ms": duration_ms,
                "output_truncated": truncated,
                "output_encoding": output_encoding,
                "decode_replacements": decode_replacements,
            },
        )


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _truncate_middle(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text.rstrip(), False
    marker = f"\n... [truncated {len(text) - limit} characters] ...\n"
    remaining = max(0, limit - len(marker))
    head = remaining // 2
    tail = remaining - head
    return (text[:head] + marker + text[-tail:]).rstrip(), True


def _decode_output(data: bytes, encodings: list[str] | None = None) -> tuple[str, str, bool]:
    candidates = encodings or _candidate_encodings()
    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding), encoding, False
        except (UnicodeDecodeError, LookupError):
            continue
    fallback = candidates[-1] if candidates else "utf-8"
    return data.decode(fallback, errors="replace"), fallback, True


def _candidate_encodings() -> list[str]:
    encodings = ["utf-8"]
    if os.name == "nt":
        try:
            import ctypes

            encodings.extend(
                [
                    f"cp{ctypes.windll.kernel32.GetOEMCP()}",
                    f"cp{ctypes.windll.kernel32.GetACP()}",
                ]
            )
        except (AttributeError, OSError):
            encodings.append("gbk")
    encodings.append(locale.getpreferredencoding(False) or "utf-8")
    return encodings
