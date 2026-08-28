"""Append-only records for one EvidenceCoder task."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
import uuid

from .api_link import ModelReply


class OperationStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    status: OperationStatus
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OperationRecord:
    op_id: str
    cycle: int
    tool: str
    arguments_digest: str
    status: OperationStatus
    summary: str
    evidence: dict[str, Any]
    started_at: str
    duration_ms: int

    @property
    def fingerprint(self) -> str:
        material = "\n".join(
            (self.tool, self.arguments_digest, self.status.value, self.summary)
        ).encode("utf-8", errors="replace")
        return hashlib.sha256(material).hexdigest()


@dataclass(slots=True)
class CycleTranscript:
    index: int
    assistant_message: dict[str, Any]
    followup_messages: list[dict[str, Any]] = field(default_factory=list)

    def api_messages(self) -> list[dict[str, Any]]:
        return [self.assistant_message, *self.followup_messages]


class RunBook:
    """The single writable record of a task.

    It is intentionally not an event bus: it has no subscribers and performs no
    dispatch. The Engine appends records; context and reporting code only read.
    """

    def __init__(self, task: str) -> None:
        self.run_id = uuid.uuid4().hex[:12]
        self.task = task
        self.started_at = _utc_now()
        self.cycles: list[CycleTranscript] = []
        self.operations: list[OperationRecord] = []
        self.summary: dict[str, Any] | None = None
        self.archived_before_cycle = 0
        self._next_operation = 1

    @property
    def current_cycle(self) -> int:
        return len(self.cycles)

    def record_assistant(self, reply: ModelReply) -> CycleTranscript:
        tool_calls = [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments_json,
                },
            }
            for call in reply.tool_calls
        ]
        message: dict[str, Any] = {"role": "assistant", "content": reply.content or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        cycle = CycleTranscript(index=len(self.cycles) + 1, assistant_message=message)
        self.cycles.append(cycle)
        return cycle

    def record_tool_message(self, call_id: str, content: dict[str, Any]) -> None:
        cycle = self._require_cycle()
        cycle.followup_messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(content, ensure_ascii=False, separators=(",", ":")),
            }
        )

    def record_control_message(self, content: str) -> None:
        cycle = self._require_cycle()
        cycle.followup_messages.append(
            {"role": "user", "content": f"[EvidenceCoder control] {content}"}
        )

    def append_operation(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        status: OperationStatus,
        summary: str,
        evidence: dict[str, Any] | None,
        started_at: str,
        duration_ms: int,
    ) -> OperationRecord:
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record = OperationRecord(
            op_id=f"op-{self._next_operation:04d}",
            cycle=self.current_cycle,
            tool=tool,
            arguments_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            status=status,
            summary=summary,
            evidence=dict(evidence or {}),
            started_at=started_at,
            duration_ms=max(0, duration_ms),
        )
        self._next_operation += 1
        self.operations.append(record)
        return record

    def operation(self, op_id: str) -> OperationRecord | None:
        return next((item for item in self.operations if item.op_id == op_id), None)

    def messages_from(self, first_cycle_index: int = 0) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for cycle in self.cycles[first_cycle_index:]:
            messages.extend(cycle.api_messages())
        return messages

    def successful_operations(self, tools: Iterable[str] | None = None) -> list[OperationRecord]:
        allowed = set(tools) if tools is not None else None
        return [
            item
            for item in self.operations
            if item.status is OperationStatus.OK and (allowed is None or item.tool in allowed)
        ]

    def archive_older_cycles(self, *, keep_last: int, summary: dict[str, Any]) -> None:
        cutoff = max(0, len(self.cycles) - keep_last)
        if cutoff <= self.archived_before_cycle:
            return
        self.summary = summary
        self.archived_before_cycle = cutoff

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "started_at": self.started_at,
            "summary": self.summary,
            "archived_before_cycle": self.archived_before_cycle,
            "cycles": [
                {
                    "index": cycle.index,
                    "assistant_message": cycle.assistant_message,
                    "followup_messages": cycle.followup_messages,
                }
                for cycle in self.cycles
            ],
            "operations": [
                {**asdict(record), "status": record.status.value} for record in self.operations
            ],
        }

    def save_json(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{self.run_id}.json"
        destination.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination

    def _require_cycle(self) -> CycleTranscript:
        if not self.cycles:
            raise RuntimeError("cannot append a follow-up message before an assistant response")
        return self.cycles[-1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
