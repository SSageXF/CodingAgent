"""Read-only, workspace-rooted Git observations."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

from ..runbook import OperationStatus, ToolOutcome


class GitTools:
    MAX_OUTPUT_CHARS = 20_000

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)

    def status(self, _arguments: dict[str, Any]) -> ToolOutcome:
        self._require_repository_root()
        output = self._run(["status", "--short", "--branch", "--untracked-files=normal"])
        rendered, truncated = _truncate(output, self.MAX_OUTPUT_CHARS)
        return ToolOutcome(
            OperationStatus.OK,
            rendered or "[clean working tree]",
            {"path": ".", "truncated": truncated},
        )

    def diff(self, arguments: dict[str, Any]) -> ToolOutcome:
        self._require_repository_root()
        command = ["diff", "--no-ext-diff", "--unified=3"]
        if arguments.get("staged", False):
            command.append("--cached")
        raw_path = arguments.get("path")
        display_path: str | None = None
        if raw_path:
            display_path = self._safe_relative_path(raw_path)
            command.extend(["--", display_path])
        output = self._run(command)
        limit = arguments.get("max_chars", 12_000)
        rendered, truncated = _truncate(output, limit)
        return ToolOutcome(
            OperationStatus.OK,
            rendered or "[no diff]",
            {
                "path": display_path or ".",
                "staged": bool(arguments.get("staged", False)),
                "truncated": truncated,
            },
        )

    def _require_repository_root(self) -> None:
        if shutil.which("git") is None:
            raise ValueError("git is not installed or not available on PATH")
        top = self._run(["rev-parse", "--show-toplevel"]).strip()
        if not top:
            raise ValueError("workspace is not a Git repository")
        if Path(top).resolve() != self.root:
            raise ValueError("workspace must be the Git repository root for Git tools")

    def _safe_relative_path(self, raw_path: object) -> str:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("Git path must be a non-empty string")
        requested = Path(raw_path)
        if requested.is_absolute() or requested.drive:
            raise ValueError("absolute Git paths are not allowed")
        resolved = (self.root / requested).resolve(strict=False)
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Git path resolves outside the workspace") from exc
        return relative.as_posix()

    def _run(self, arguments: list[str]) -> str:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *arguments],
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=False,
        )
        output = (result.stdout or b"").decode("utf-8", errors="replace").rstrip()
        if result.returncode != 0:
            detail = output[:500] or f"exit code {result.returncode}"
            raise ValueError(f"git command failed: {detail}")
        return output


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    marker = f"\n... [truncated {len(text) - limit} characters] ...\n"
    remaining = max(0, limit - len(marker))
    head = remaining // 2
    return text[:head] + marker + text[-(remaining - head) :], True
