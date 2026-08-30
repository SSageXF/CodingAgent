from __future__ import annotations

import json
import sys
from typing import Any, Sequence

from evidencecoder.api_link import ModelReply, ModelToolCall
from evidencecoder.context_window import ContextWindow
from evidencecoder.engine import Engine, RunStatus
from evidencecoder.runbook import OperationStatus, RunBook
from evidencecoder.settings import Settings


class FakeGateway:
    def __init__(self, replies: list[ModelReply]) -> None:
        self.replies = list(replies)
        self.requests: list[tuple[Sequence[dict[str, Any]], Sequence[dict[str, Any]]]] = []

    def complete(self, messages, tools):
        self.requests.append((messages, tools))
        if not self.replies:
            raise AssertionError("fake gateway has no reply left")
        return self.replies.pop(0)


def call(call_id: str, name: str, arguments: dict[str, Any]) -> ModelReply:
    return ModelReply(
        "",
        (ModelToolCall(call_id, name, json.dumps(arguments)),),
    )


def settings_for(tmp_path, **changes):
    base = Settings(
        workspace=tmp_path,
        model="fake",
        base_url="https://example.test/v1",
        save_run_log=False,
        auto_approve_writes=True,
        auto_approve_commands=True,
    )
    return base.with_overrides(**changes)


def test_full_engine_loop_requires_evidence_and_completes(tmp_path):
    check_command = f'"{sys.executable}" -c "print(\'ok\')"'
    gateway = FakeGateway(
        [
            call(
                "c1",
                "write_text",
                {"path": "answer.py", "content": "print('answer')\n"},
            ),
            call("c2", "run_local", {"command": check_command}),
            call(
                "c3",
                "submit_result",
                {
                    "summary": "implemented and checked",
                    "changed_files": ["answer.py"],
                    "checks": [check_command],
                    "evidence_ids": ["op-0001", "op-0002"],
                    "limitations": [],
                },
            ),
        ]
    )
    result = Engine(settings_for(tmp_path), gateway).run("create answer.py")
    assert result.status is RunStatus.COMPLETED
    assert result.completion is not None
    assert result.completion["evidence_ids"] == ["op-0001", "op-0002"]
    assert (tmp_path / "answer.py").exists()
    assert [item.tool for item in result.runbook.operations] == [
        "write_text",
        "run_local",
        "submit_result",
    ]


def test_prior_context_and_platform_facts_are_projected(tmp_path):
    gateway = FakeGateway([ModelReply("done"), ModelReply("done"), ModelReply("done")])
    Engine(settings_for(tmp_path), gateway).run(
        "continue", prior_context={"verified_entries": [{"summary": "created x.py"}]}
    )
    first_messages = gateway.requests[0][0]
    assert "Local execution platform facts" in first_messages[1]["content"]
    assert "recommended_python_command" in first_messages[1]["content"]
    assert "created x.py" in first_messages[2]["content"]


def test_approval_wait_is_not_counted_as_execution_time(tmp_path):
    gateway = FakeGateway(
        [call("c1", "write_text", {"path": "x.txt", "content": "x"})]
    )

    def approve(*_):
        import time

        time.sleep(0.05)
        return True

    result = Engine(
        settings_for(tmp_path, auto_approve_writes=False, max_cycles=1),
        gateway,
        approval=approve,
    ).run("write x")
    record = result.runbook.operations[0]
    assert record.approval_wait_ms >= 40
    assert record.duration_ms < record.approval_wait_ms


def test_unapproved_write_is_recorded_as_denied(tmp_path):
    gateway = FakeGateway(
        [call("c1", "write_text", {"path": "x", "content": "no"})]
    )
    result = Engine(
        settings_for(tmp_path, auto_approve_writes=False, max_cycles=1),
        gateway,
        approval=lambda *_: False,
    ).run("write x")
    assert result.status is RunStatus.BUDGET_EXHAUSTED
    assert result.runbook.operations[0].status.value == "denied"
    assert not (tmp_path / "x").exists()


def test_three_plain_text_replies_stall(tmp_path):
    gateway = FakeGateway([ModelReply("done"), ModelReply("done"), ModelReply("done")])
    result = Engine(settings_for(tmp_path), gateway).run("do something")
    assert result.status is RunStatus.STALLED
    assert "no tool calls" in result.summary


def test_repeated_identical_operations_stall(tmp_path):
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    repeated = [
        call(f"c{index}", "read_segment", {"path": "x.txt"}) for index in range(1, 4)
    ]
    result = Engine(settings_for(tmp_path, max_repeated_operation=3), FakeGateway(repeated)).run(
        "read forever"
    )
    assert result.status is RunStatus.STALLED
    assert "repeated" in result.summary


def test_context_compaction_preserves_operation_facts(tmp_path):
    book = RunBook("goal")
    for index in range(4):
        book.record_assistant(ModelReply("long text " * 50))
        book.append_operation(
            tool="read_segment",
            arguments={"path": f"{index}.txt"},
            status=OperationStatus.OK,
            summary=f"read {index}",
            evidence={"path": f"{index}.txt"},
            started_at="now",
            duration_ms=1,
        )
    summary_reply = ModelReply(
        json.dumps(
            {
                "goal": "goal",
                "confirmed_facts": ["fact"],
                "changed_files": [],
                "failed_attempts": [],
                "pending": ["work"],
            }
        )
    )
    gateway = FakeGateway([summary_reply])
    window = ContextWindow(soft_limit_tokens=1, keep_cycles=1)
    assert window.compact_if_needed(book, gateway) is True
    assert book.archived_before_cycle == 3
    assert book.summary is not None
    assert len(book.summary["verified_operations"]) == 3
    messages = window.compose(book)
    assert any("Earlier verified run summary" in message["content"] for message in messages)
    assert len(messages) == 5
