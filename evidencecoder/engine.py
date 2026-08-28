"""The explicit COMPOSE → ASK → CHECK → AUTHORIZE → ACT → ASSESS loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Callable

from .api_link import APIError, ModelGateway
from .context_window import ContextWindow
from .guard import Guard, GuardAction
from .runbook import OperationRecord, OperationStatus, RunBook, ToolOutcome
from .settings import Settings
from .tool_impl import LocalCommands, WorkspaceFiles
from .toolbox import ToolArgumentsError, Toolbox, UnknownToolError


class RunStatus(str, Enum):
    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STALLED = "stalled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentResult:
    status: RunStatus
    summary: str
    runbook: RunBook
    completion: dict[str, Any] | None = None
    log_path: str | None = None


ApprovalCallback = Callable[[str, dict[str, Any], str], bool]
Observer = Callable[[str], None]


class Engine:
    """Own all mutable control flow for one single-agent run."""

    def __init__(
        self,
        settings: Settings,
        gateway: ModelGateway,
        *,
        approval: ApprovalCallback | None = None,
        observer: Observer | None = None,
        toolbox: Toolbox | None = None,
    ) -> None:
        self.settings = settings
        self.gateway = gateway
        self.approval = approval or (lambda _tool, _arguments, _reason: False)
        self.observer = observer or (lambda _message: None)
        self.toolbox = toolbox or Toolbox(
            WorkspaceFiles(settings.workspace),
            LocalCommands(settings.workspace, settings.command_timeout_seconds),
        )
        self.guard = Guard(
            auto_approve_writes=settings.auto_approve_writes,
            auto_approve_commands=settings.auto_approve_commands,
        )
        self.context = ContextWindow(
            soft_limit_tokens=settings.context_soft_limit_tokens,
            keep_cycles=settings.context_keep_cycles,
        )

    def run(self, task: str) -> AgentResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        self.settings.validate()
        runbook = RunBook(task.strip())
        started = time.monotonic()
        consecutive_errors = 0
        protocol_errors = 0

        try:
            for cycle_index in range(1, self.settings.max_cycles + 1):
                if time.monotonic() - started >= self.settings.wall_time_seconds:
                    return self._finish(
                        runbook,
                        RunStatus.BUDGET_EXHAUSTED,
                        "wall-clock time budget exhausted",
                    )

                self.context.compact_if_needed(runbook, self.gateway)
                messages = self.context.compose(runbook)
                self.observer(f"cycle {cycle_index}: asking model")
                try:
                    reply = self.gateway.complete(messages, self.toolbox.api_specs)
                except APIError as exc:
                    return self._finish(runbook, RunStatus.FAILED, str(exc))

                runbook.record_assistant(reply)
                if not reply.tool_calls:
                    protocol_errors += 1
                    runbook.record_control_message(
                        "No tool call was supplied. Continue with a tool, or use submit_result "
                        "with valid evidence when the task is complete."
                    )
                    if protocol_errors >= 3:
                        return self._finish(
                            runbook,
                            RunStatus.STALLED,
                            "model returned no tool calls three times in succession",
                        )
                    continue

                protocol_errors = 0
                for call in reply.tool_calls:
                    outcome, record = self._handle_call(runbook, call.name, call.arguments_json)
                    runbook.record_tool_message(
                        call.call_id,
                        {
                            "op_id": record.op_id,
                            "status": outcome.status.value,
                            "summary": outcome.summary,
                            "evidence": outcome.evidence,
                        },
                    )
                    self.observer(
                        f"{record.op_id} {call.name}: {outcome.status.value} — {outcome.summary}"
                    )

                    if outcome.status is OperationStatus.OK:
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1

                    if call.name == "submit_result" and outcome.status is OperationStatus.OK:
                        return self._finish(
                            runbook,
                            RunStatus.COMPLETED,
                            outcome.summary,
                            completion=outcome.evidence,
                        )
                    if consecutive_errors >= self.settings.max_consecutive_tool_errors:
                        return self._finish(
                            runbook,
                            RunStatus.STALLED,
                            f"{consecutive_errors} consecutive tool errors",
                        )
                    if self._is_repeating(runbook):
                        return self._finish(
                            runbook,
                            RunStatus.STALLED,
                            "the same tool operation and result repeated too many times",
                        )

            return self._finish(
                runbook,
                RunStatus.BUDGET_EXHAUSTED,
                f"maximum model cycles reached ({self.settings.max_cycles})",
            )
        except KeyboardInterrupt:
            return self._finish(runbook, RunStatus.CANCELLED, "cancelled by user")
        except Exception as exc:
            return self._finish(runbook, RunStatus.FAILED, f"unexpected error: {exc}")

    def _handle_call(
        self, runbook: RunBook, tool: str, arguments_json: str
    ) -> tuple[ToolOutcome, OperationRecord]:
        started_at = _utc_now()
        started = time.monotonic()
        arguments: dict[str, Any]
        try:
            arguments = self.toolbox.parse_and_validate(tool, arguments_json)
        except (ToolArgumentsError, UnknownToolError) as exc:
            arguments = {"raw_arguments": arguments_json}
            outcome = ToolOutcome(OperationStatus.ERROR, str(exc), {})
            return outcome, self._record(
                runbook, tool, arguments, outcome, started_at, started
            )

        decision = self.guard.assess(tool, arguments)
        if decision.action is GuardAction.DENY:
            outcome = ToolOutcome(
                OperationStatus.DENIED,
                f"denied by safety policy: {decision.reason}",
                {},
            )
        elif decision.action is GuardAction.ASK and not self.approval(
            tool, arguments, decision.reason
        ):
            outcome = ToolOutcome(
                OperationStatus.DENIED,
                f"not approved by user: {decision.reason}",
                {},
            )
        else:
            outcome = self.toolbox.execute(tool, arguments, runbook)
        return outcome, self._record(runbook, tool, arguments, outcome, started_at, started)

    @staticmethod
    def _record(
        runbook: RunBook,
        tool: str,
        arguments: dict[str, Any],
        outcome: ToolOutcome,
        started_at: str,
        started: float,
    ) -> OperationRecord:
        return runbook.append_operation(
            tool=tool,
            arguments=arguments,
            status=outcome.status,
            summary=outcome.summary,
            evidence=outcome.evidence,
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1_000),
        )

    def _is_repeating(self, runbook: RunBook) -> bool:
        count = self.settings.max_repeated_operation
        if len(runbook.operations) < count:
            return False
        tail = runbook.operations[-count:]
        return len({record.fingerprint for record in tail}) == 1

    def _finish(
        self,
        runbook: RunBook,
        status: RunStatus,
        summary: str,
        *,
        completion: dict[str, Any] | None = None,
    ) -> AgentResult:
        log_path: str | None = None
        if self.settings.save_run_log:
            try:
                path = runbook.save_json(self.settings.workspace / ".evidencecoder" / "runs")
                log_path = str(path)
            except OSError as exc:
                summary = f"{summary} (run log could not be saved: {exc})"
        return AgentResult(status, summary, runbook, completion, log_path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
