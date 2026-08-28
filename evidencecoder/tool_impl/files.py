"""Workspace-bounded file inspection and editing tools."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterable
import uuid

from ..runbook import OperationStatus, ToolOutcome


class FileToolError(ValueError):
    """A file request is invalid or cannot be completed safely."""


class WorkspaceFiles:
    MAX_TEXT_BYTES = 1_000_000
    MAX_READ_LINES = 400
    MAX_WRITE_BYTES = 1_000_000

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise FileToolError(f"workspace is not a directory: {self.root}")

    def resolve(self, relative_path: str, *, for_write: bool = False) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise FileToolError("path must be a non-empty string")
        requested = Path(relative_path)
        if requested.is_absolute() or requested.drive:
            raise FileToolError("absolute paths are not allowed")
        candidate = self.root.joinpath(requested)
        resolved = candidate.resolve(strict=False)
        if not _is_inside(resolved, self.root):
            raise FileToolError("path resolves outside the workspace")
        if not for_write and not resolved.exists():
            raise FileToolError(f"path does not exist: {relative_path}")
        return resolved

    def inspect_tree(self, arguments: dict[str, Any]) -> ToolOutcome:
        relative_path = arguments.get("path", ".")
        max_depth = arguments.get("max_depth", 3)
        max_entries = arguments.get("max_entries", 200)
        start = self.resolve(relative_path)
        if not start.is_dir():
            raise FileToolError("inspect_tree path must be a directory")

        entries: list[str] = []
        ignored = {".git", ".evidencecoder", "__pycache__", ".pytest_cache"}
        start_depth = len(start.parts)
        for current, dirnames, filenames in os.walk(start, followlinks=False):
            current_path = Path(current)
            depth = len(current_path.parts) - start_depth
            dirnames[:] = sorted(name for name in dirnames if name not in ignored)
            if depth >= max_depth:
                dirnames[:] = []
            for dirname in dirnames:
                entries.append(self._display(current_path / dirname) + "/")
                if len(entries) >= max_entries:
                    break
            if len(entries) >= max_entries:
                break
            for filename in sorted(filenames):
                entries.append(self._display(current_path / filename))
                if len(entries) >= max_entries:
                    break
            if len(entries) >= max_entries:
                break

        truncated = len(entries) >= max_entries
        summary = "\n".join(entries) if entries else "[empty directory]"
        if truncated:
            summary += f"\n[truncated at {max_entries} entries]"
        return ToolOutcome(
            OperationStatus.OK,
            summary,
            {"path": self._display(start), "entry_count": len(entries), "truncated": truncated},
        )

    def read_segment(self, arguments: dict[str, Any]) -> ToolOutcome:
        path = self.resolve(arguments["path"])
        if not path.is_file():
            raise FileToolError("read_segment path must be a regular file")
        size = path.stat().st_size
        if size > self.MAX_TEXT_BYTES:
            raise FileToolError(f"file is larger than {self.MAX_TEXT_BYTES} bytes")
        start_line = arguments.get("start_line", 1)
        end_line = arguments.get("end_line", start_line + 199)
        if end_line < start_line:
            raise FileToolError("end_line must be greater than or equal to start_line")
        if end_line - start_line + 1 > self.MAX_READ_LINES:
            raise FileToolError(f"a read may include at most {self.MAX_READ_LINES} lines")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FileToolError("file is not valid UTF-8 text") from exc
        lines = text.splitlines()
        selected = lines[start_line - 1 : end_line]
        rendered = "\n".join(
            f"{line_number:>6} | {line}"
            for line_number, line in enumerate(selected, start=start_line)
        )
        if not rendered:
            rendered = "[no lines in requested range]"
        return ToolOutcome(
            OperationStatus.OK,
            rendered,
            {
                "path": self._display(path),
                "start_line": start_line,
                "end_line": min(end_line, len(lines)),
                "total_lines": len(lines),
                "sha256": _sha256_bytes(text.encode("utf-8")),
            },
        )

    def find_matches(self, arguments: dict[str, Any]) -> ToolOutcome:
        pattern = arguments["pattern"]
        relative_path = arguments.get("path", ".")
        file_glob = arguments.get("glob")
        max_matches = arguments.get("max_matches", 100)
        start = self.resolve(relative_path)
        if shutil.which("rg"):
            matches, truncated = self._find_with_rg(
                pattern, start, file_glob=file_glob, max_matches=max_matches
            )
        else:
            matches, truncated = self._find_with_python(
                pattern, start, file_glob=file_glob, max_matches=max_matches
            )
        summary = "\n".join(matches) if matches else "[no matches]"
        if truncated:
            summary += f"\n[truncated at {max_matches} matches]"
        return ToolOutcome(
            OperationStatus.OK,
            summary,
            {
                "path": self._display(start),
                "pattern": pattern,
                "match_count": len(matches),
                "truncated": truncated,
            },
        )

    def replace_text(self, arguments: dict[str, Any]) -> ToolOutcome:
        path = self.resolve(arguments["path"], for_write=True)
        if not path.is_file():
            raise FileToolError("replace_text path must be an existing regular file")
        old_text = arguments["old_text"]
        new_text = arguments["new_text"]
        expected_count = arguments.get("expected_count", 1)
        if old_text == new_text:
            raise FileToolError("old_text and new_text must be different")
        if path.stat().st_size > self.MAX_TEXT_BYTES:
            raise FileToolError(f"file is larger than {self.MAX_TEXT_BYTES} bytes")
        try:
            before = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FileToolError("file is not valid UTF-8 text") from exc
        actual_count = before.count(old_text)
        if actual_count != expected_count:
            raise FileToolError(
                f"expected {expected_count} exact matches but found {actual_count}; reread the file"
            )
        after = before.replace(old_text, new_text, expected_count)
        self._atomic_write(path, after)
        return ToolOutcome(
            OperationStatus.OK,
            f"replaced {actual_count} occurrence(s) in {self._display(path)}",
            {
                "path": self._display(path),
                "replacement_count": actual_count,
                "before_sha256": _sha256_bytes(before.encode("utf-8")),
                "after_sha256": _sha256_bytes(after.encode("utf-8")),
            },
        )

    def write_text(self, arguments: dict[str, Any]) -> ToolOutcome:
        path = self.resolve(arguments["path"], for_write=True)
        content = arguments["content"]
        overwrite = arguments.get("overwrite", False)
        create_parents = arguments.get("create_parents", False)
        encoded = content.encode("utf-8")
        if len(encoded) > self.MAX_WRITE_BYTES:
            raise FileToolError(f"content is larger than {self.MAX_WRITE_BYTES} bytes")
        if path.exists() and not path.is_file():
            raise FileToolError("write_text target is not a regular file")
        if path.exists() and not overwrite:
            raise FileToolError("target already exists; set overwrite=true only after reading it")
        if not path.parent.exists():
            if not create_parents:
                raise FileToolError("parent directory does not exist")
            path.parent.mkdir(parents=True, exist_ok=True)
        before_hash = _sha256_file(path) if path.exists() else None
        self._atomic_write(path, content)
        return ToolOutcome(
            OperationStatus.OK,
            f"wrote {len(encoded)} bytes to {self._display(path)}",
            {
                "path": self._display(path),
                "bytes": len(encoded),
                "created": before_hash is None,
                "before_sha256": before_hash,
                "after_sha256": _sha256_bytes(encoded),
            },
        )

    def _find_with_rg(
        self, pattern: str, start: Path, *, file_glob: str | None, max_matches: int
    ) -> tuple[list[str], bool]:
        command = [
            "rg",
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--glob",
            "!.git/**",
            "--glob",
            "!.evidencecoder/**",
        ]
        if file_glob:
            command.extend(["--glob", file_glob])
        command.extend(["--", pattern, str(start)])
        result = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        if result.returncode not in {0, 1}:
            raise FileToolError(f"rg failed: {result.stderr.strip()[:500]}")
        raw_lines = result.stdout.splitlines()
        rendered = [self._make_search_result_relative(line) for line in raw_lines[:max_matches]]
        return rendered, len(raw_lines) > max_matches

    def _find_with_python(
        self, pattern: str, start: Path, *, file_glob: str | None, max_matches: int
    ) -> tuple[list[str], bool]:
        candidates: Iterable[Path]
        if start.is_file():
            candidates = [start]
        else:
            candidates = start.rglob(file_glob or "*")
        matches: list[str] = []
        for path in candidates:
            if not path.is_file() or any(part in {".git", ".evidencecoder"} for part in path.parts):
                continue
            if path.stat().st_size > self.MAX_TEXT_BYTES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, start=1):
                if pattern in line:
                    matches.append(f"{self._display(path)}:{number}:{line}")
                    if len(matches) > max_matches:
                        return matches[:max_matches], True
        return matches, False

    def _make_search_result_relative(self, line: str) -> str:
        normalized_root = str(self.root)
        if line.lower().startswith(normalized_root.lower()):
            line = line[len(normalized_root) :].lstrip("\\/")
        return line.replace("\\", "/")

    def _display(self, path: Path) -> str:
        relative = path.resolve(strict=False).relative_to(self.root)
        return relative.as_posix() or "."

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.evidencecoder-{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8", newline="")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


def _is_inside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())
