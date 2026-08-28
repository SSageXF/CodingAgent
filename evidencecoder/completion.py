"""Validation of model completion claims against recorded local evidence."""

from __future__ import annotations

from typing import Any

from .runbook import OperationStatus, RunBook, ToolOutcome


class CompletionVerifier:
    WRITE_TOOLS = {"replace_text", "write_text"}

    def verify(self, arguments: dict[str, Any], runbook: RunBook) -> ToolOutcome:
        evidence_ids = arguments["evidence_ids"]
        if len(set(evidence_ids)) != len(evidence_ids):
            return self._error("evidence_ids must not contain duplicates")
        records = []
        for op_id in evidence_ids:
            record = runbook.operation(op_id)
            if record is None:
                return self._error(f"unknown evidence id: {op_id}")
            if record.status is not OperationStatus.OK:
                return self._error(f"evidence {op_id} did not succeed: {record.status.value}")
            records.append(record)

        changed_files = {_normal_path(path) for path in arguments["changed_files"]}
        evidenced_files = {
            _normal_path(str(record.evidence.get("path", "")))
            for record in records
            if record.tool in self.WRITE_TOOLS and record.evidence.get("path")
        }
        missing_files = sorted(changed_files - evidenced_files)
        if missing_files:
            return self._error(
                "changed files lack successful write evidence: " + ", ".join(missing_files)
            )

        operation_positions = {record.op_id: index for index, record in enumerate(runbook.operations)}
        referenced_ids = set(evidence_ids)
        latest_write_positions: list[int] = []
        for changed_file in changed_files:
            successful_writes = [
                record
                for record in runbook.operations
                if record.status is OperationStatus.OK
                and record.tool in self.WRITE_TOOLS
                and _normal_path(str(record.evidence.get("path", ""))) == changed_file
            ]
            latest = successful_writes[-1]
            if latest.op_id not in referenced_ids:
                return self._error(
                    f"latest successful write for {changed_file} is not referenced: {latest.op_id}"
                )
            latest_write_positions.append(operation_positions[latest.op_id])

        checks = arguments["checks"]
        successful_commands = [
            record
            for record in records
            if record.tool == "run_local" and record.evidence.get("exit_code") == 0
        ]
        if checks and not successful_commands:
            return self._error("checks were claimed without a referenced command that exited 0")
        if checks and latest_write_positions:
            last_write = max(latest_write_positions)
            if not any(operation_positions[record.op_id] > last_write for record in successful_commands):
                return self._error("checks were run before the latest referenced file change")

        return ToolOutcome(
            OperationStatus.OK,
            arguments["summary"],
            {
                "changed_files": sorted(changed_files),
                "checks": checks,
                "evidence_ids": evidence_ids,
                "limitations": arguments["limitations"],
                "verified_command_count": len(successful_commands),
            },
        )

    @staticmethod
    def _error(message: str) -> ToolOutcome:
        return ToolOutcome(OperationStatus.ERROR, f"completion rejected: {message}", {})


def _normal_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized
