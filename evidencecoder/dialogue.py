"""Persistent, verified context shared between independent agent runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from .engine import AgentResult


FORMAT_VERSION = 1
_DIALOGUE_ID = re.compile(r"^[a-f0-9]{12}$")


class DialogueError(ValueError):
    """A saved dialogue is missing, invalid, or belongs to another workspace."""


@dataclass(frozen=True, slots=True)
class DialogueEntry:
    instruction: str
    run_id: str
    status: str
    summary: str
    changed_files: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("changed_files", "checks", "limitations"):
            value[key] = list(value[key])
        return value


@dataclass(slots=True)
class DialogueBook:
    dialogue_id: str
    workspace_fingerprint: str
    created_at: str
    updated_at: str
    entries: list[DialogueEntry] = field(default_factory=list)
    format_version: int = FORMAT_VERSION

    @classmethod
    def create(cls, workspace: Path | str) -> "DialogueBook":
        now = _utc_now()
        return cls(
            dialogue_id=uuid.uuid4().hex[:12],
            workspace_fingerprint=_workspace_fingerprint(workspace),
            created_at=now,
            updated_at=now,
        )

    def append_result(self, instruction: str, result: "AgentResult") -> DialogueEntry:
        completion = result.completion or {}
        entry = DialogueEntry(
            instruction=instruction.strip(),
            run_id=result.runbook.run_id,
            status=result.status.value,
            summary=result.summary,
            changed_files=tuple(str(item) for item in completion.get("changed_files", [])),
            checks=tuple(str(item) for item in completion.get("checks", [])),
            limitations=tuple(str(item) for item in completion.get("limitations", [])),
            completed_at=_utc_now(),
        )
        self.entries.append(entry)
        self.updated_at = entry.completed_at
        return entry

    def project(self, *, keep_last: int = 8) -> dict[str, Any]:
        """Return bounded context with no operation IDs or raw tool output."""

        selected = self.entries[-max(1, keep_last) :]
        return {
            "dialogue_id": self.dialogue_id,
            "completed_tasks": [
                {
                    "instruction": entry.instruction,
                    "summary": entry.summary,
                    "changed_files": list(entry.changed_files),
                    "checks": list(entry.checks),
                    "limitations": list(entry.limitations),
                }
                for entry in selected
                if entry.status == "completed"
            ],
            "recent_incomplete_attempts": [
                {
                    "instruction": entry.instruction,
                    "status": entry.status,
                    "summary": entry.summary,
                }
                for entry in selected
                if entry.status != "completed"
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "dialogue_id": self.dialogue_id,
            "workspace_fingerprint": self.workspace_fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }


class DialogueStore:
    def __init__(self, workspace: Path | str) -> None:
        self.workspace = Path(workspace).expanduser().resolve(strict=True)
        self.directory = self.workspace / ".evidencecoder" / "dialogues"
        self.workspace_fingerprint = _workspace_fingerprint(self.workspace)

    def save(self, book: DialogueBook) -> Path:
        self._verify_workspace(book)
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{book.dialogue_id}.json"
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(book.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="",
            )
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return destination

    def load(self, selector: str) -> DialogueBook:
        path = self._resolve_selector(selector)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DialogueError(f"cannot read dialogue {selector}: {exc}") from exc
        book = _book_from_dict(data)
        self._verify_workspace(book)
        return book

    def _resolve_selector(self, selector: str) -> Path:
        if selector == "latest":
            if not self.directory.is_dir():
                raise DialogueError("no saved dialogues exist in this workspace")
            candidates = sorted(
                self.directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True
            )
            if not candidates:
                raise DialogueError("no saved dialogues exist in this workspace")
            return candidates[0]
        if not _DIALOGUE_ID.fullmatch(selector):
            raise DialogueError("dialogue id must be 12 lowercase hexadecimal characters")
        path = self.directory / f"{selector}.json"
        if not path.is_file():
            raise DialogueError(f"dialogue not found: {selector}")
        return path

    def _verify_workspace(self, book: DialogueBook) -> None:
        if book.workspace_fingerprint != self.workspace_fingerprint:
            raise DialogueError("dialogue belongs to a different workspace")


def _book_from_dict(data: object) -> DialogueBook:
    if not isinstance(data, dict) or data.get("format_version") != FORMAT_VERSION:
        raise DialogueError("unsupported or missing dialogue format_version")
    required = {"dialogue_id", "workspace_fingerprint", "created_at", "updated_at", "entries"}
    if not required.issubset(data) or not isinstance(data["entries"], list):
        raise DialogueError("dialogue file is missing required fields")
    if not _DIALOGUE_ID.fullmatch(str(data["dialogue_id"])):
        raise DialogueError("dialogue file has an invalid id")
    entries: list[DialogueEntry] = []
    for raw in data["entries"]:
        if not isinstance(raw, dict):
            raise DialogueError("dialogue entry must be an object")
        try:
            entries.append(
                DialogueEntry(
                    instruction=str(raw["instruction"]),
                    run_id=str(raw["run_id"]),
                    status=str(raw["status"]),
                    summary=str(raw["summary"]),
                    changed_files=tuple(str(item) for item in raw.get("changed_files", [])),
                    checks=tuple(str(item) for item in raw.get("checks", [])),
                    limitations=tuple(str(item) for item in raw.get("limitations", [])),
                    completed_at=str(raw["completed_at"]),
                )
            )
        except (KeyError, TypeError) as exc:
            raise DialogueError("dialogue entry is missing required fields") from exc
    return DialogueBook(
        format_version=FORMAT_VERSION,
        dialogue_id=str(data["dialogue_id"]),
        workspace_fingerprint=str(data["workspace_fingerprint"]),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
        entries=entries,
    )


def _workspace_fingerprint(workspace: Path | str) -> str:
    normalized = str(Path(workspace).expanduser().resolve(strict=True))
    if os.name == "nt":
        normalized = normalized.casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
