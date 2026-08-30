from __future__ import annotations

import json
import os
from typing import Any, Sequence

import pytest

from evidencecoder.api_link import ModelReply, ModelToolCall
from evidencecoder.dialogue import DialogueBook, DialogueError, DialogueStore
from evidencecoder.engine import AgentResult, Engine, RunStatus
from evidencecoder.interactive import ApprovalManager, InteractiveShell
from evidencecoder.runbook import RunBook
from evidencecoder.settings import Settings


class FakeGateway:
    def __init__(self, replies: list[ModelReply]) -> None:
        self.replies = list(replies)
        self.requests: list[Sequence[dict[str, Any]]] = []

    def complete(self, messages, tools):
        self.requests.append(messages)
        return self.replies.pop(0)


def tool(call_id: str, name: str, arguments: dict[str, Any]) -> ModelReply:
    return ModelReply("", (ModelToolCall(call_id, name, json.dumps(arguments)),))


def settings_for(tmp_path, **changes) -> Settings:
    settings = Settings(
        workspace=tmp_path,
        model="fake",
        base_url="https://example.test/v1",
        auto_approve_writes=True,
        auto_approve_commands=True,
    )
    return settings.with_overrides(**changes)


def completed_result(task: str = "first") -> AgentResult:
    book = RunBook(task)
    return AgentResult(
        RunStatus.COMPLETED,
        "verified summary",
        book,
        {
            "changed_files": ["answer.py"],
            "checks": ["python -m pytest"],
            "limitations": [],
        },
    )


def test_dialogue_round_trip_and_projection_omit_operation_ids(tmp_path):
    store = DialogueStore(tmp_path)
    book = DialogueBook.create(tmp_path)
    book.append_result("create answer", completed_result())
    path = store.save(book)

    loaded = store.load(book.dialogue_id)
    projection = loaded.project()
    serialized = json.dumps(projection)
    assert loaded.dialogue_id == book.dialogue_id
    assert projection["completed_tasks"][0]["summary"] == "verified summary"
    assert "run_id" not in serialized
    assert "op-" not in serialized
    assert path == store.directory / f"{book.dialogue_id}.json"


def test_dialogue_rejects_wrong_workspace_and_unknown_format(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    book = DialogueBook.create(first)
    path = DialogueStore(first).save(book)

    foreign_directory = second / ".evidencecoder" / "dialogues"
    foreign_directory.mkdir(parents=True)
    foreign_path = foreign_directory / path.name
    foreign_path.write_bytes(path.read_bytes())
    with pytest.raises(DialogueError, match="different workspace"):
        DialogueStore(second).load(book.dialogue_id)

    data = json.loads(path.read_text(encoding="utf-8"))
    data["format_version"] = 999
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DialogueError, match="format_version"):
        DialogueStore(first).load(book.dialogue_id)


def test_interactive_two_tasks_share_only_verified_dialogue_context(tmp_path):
    gateway = FakeGateway(
        [
            tool("a1", "inspect_tree", {}),
            tool(
                "a2",
                "submit_result",
                {
                    "summary": "first verified",
                    "changed_files": [],
                    "checks": [],
                    "evidence_ids": ["op-0001"],
                    "limitations": [],
                },
            ),
            tool("b1", "inspect_tree", {}),
            tool(
                "b2",
                "submit_result",
                {
                    "summary": "second verified",
                    "changed_files": [],
                    "checks": [],
                    "evidence_ids": ["op-0001"],
                    "limitations": [],
                },
            ),
        ]
    )
    answers = iter(["inspect first", "inspect again", "/exit"])
    output: list[str] = []
    shell = InteractiveShell(
        settings_for(tmp_path),
        gateway,
        input_fn=lambda _: next(answers),
        output=output.append,
    )
    assert shell.run() == 0
    assert len(shell.dialogue.entries) == 2
    assert shell.dialogue.entries[0].run_id != shell.dialogue.entries[1].run_id
    second_task_first_request = gateway.requests[2]
    assert any("first verified" in message["content"] for message in second_task_first_request)
    assert DialogueStore(tmp_path).load("latest").dialogue_id == shell.dialogue.dialogue_id


def test_old_operation_id_cannot_complete_a_new_run(tmp_path):
    old_context = {
        "completed_tasks": [{"summary": "old run used op-0002"}],
    }
    gateway = FakeGateway(
        [
            tool(
                "new1",
                "submit_result",
                {
                    "summary": "unsupported",
                    "changed_files": [],
                    "checks": [],
                    "evidence_ids": ["op-0002"],
                    "limitations": [],
                },
            )
        ]
    )
    result = Engine(settings_for(tmp_path, max_cycles=1), gateway).run(
        "continue", prior_context=old_context
    )
    assert result.status is RunStatus.BUDGET_EXHAUSTED
    assert "unknown evidence id" in result.runbook.operations[0].summary


def test_new_dialogue_keeps_workspace_files(tmp_path):
    marker = tmp_path / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    answers = iter(["/new", "/exit"])
    shell = InteractiveShell(
        settings_for(tmp_path),
        FakeGateway([]),
        input_fn=lambda _: next(answers),
        output=lambda _: None,
    )
    original_id = shell.dialogue.dialogue_id
    shell.run()
    assert marker.read_text(encoding="utf-8") == "keep"
    assert shell.dialogue.dialogue_id != original_id


def test_approval_all_is_category_scoped_and_quit_interrupts():
    answers = iter(["a", "a"])
    manager = ApprovalManager(input_fn=lambda _: next(answers), output=lambda _: None)
    assert manager("write_text", {"path": "a"}, "write") is True
    assert manager("replace_text", {"path": "a"}, "write") is True
    assert manager("run_local", {"command": "ok"}, "command") is True
    assert manager("run_local", {"command": "another"}, "command") is True

    quitting = ApprovalManager(input_fn=lambda _: "q", output=lambda _: None)
    with pytest.raises(KeyboardInterrupt):
        quitting("run_local", {"command": "stop"}, "command")


def test_retry_repeats_last_instruction_and_export_writes_report(tmp_path):
    gateway = FakeGateway(
        [
            tool("a1", "inspect_tree", {}),
            tool(
                "a2",
                "submit_result",
                {
                    "summary": "first result",
                    "changed_files": [],
                    "checks": [],
                    "evidence_ids": ["op-0001"],
                    "limitations": [],
                },
            ),
            tool("b1", "inspect_tree", {}),
            tool(
                "b2",
                "submit_result",
                {
                    "summary": "retry result",
                    "changed_files": [],
                    "checks": [],
                    "evidence_ids": ["op-0001"],
                    "limitations": [],
                },
            ),
        ]
    )
    answers = iter(["inspect project", "/retry", "/export report.md", "/exit"])
    output: list[str] = []
    shell = InteractiveShell(
        settings_for(tmp_path),
        gateway,
        input_fn=lambda _: next(answers),
        output=output.append,
    )
    assert shell.run() == 0
    assert [entry.instruction for entry in shell.dialogue.entries] == [
        "inspect project",
        "inspect project",
    ]
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "first result" in report
    assert "retry result" in report
    assert "Usage:" in report


def test_resume_without_argument_lists_and_selects_dialogue(tmp_path):
    store = DialogueStore(tmp_path)
    older = DialogueBook.create(tmp_path)
    older.append_result("older context", completed_result("older"))
    older_path = store.save(older)
    newer = DialogueBook.create(tmp_path)
    newer.append_result("newer context", completed_result("newer"))
    newer_path = store.save(newer)
    os.utime(older_path, (1, 1))
    os.utime(newer_path, (2, 2))

    answers = iter(["/resume", "2", "/exit"])
    output: list[str] = []
    shell = InteractiveShell(
        settings_for(tmp_path),
        FakeGateway([]),
        input_fn=lambda _: next(answers),
        output=output.append,
    )
    assert shell.run() == 0
    assert shell.dialogue.dialogue_id == older.dialogue_id
    assert any("1. [completed] newer context" in line for line in output)
    assert any("2. [completed] older context" in line for line in output)


def test_resume_latest_remains_supported_and_invalid_files_are_skipped(tmp_path):
    store = DialogueStore(tmp_path)
    book = DialogueBook.create(tmp_path)
    book.append_result("latest context", completed_result())
    store.save(book)
    (store.directory / "broken.json").write_text("not json", encoding="utf-8")

    shell = InteractiveShell(
        settings_for(tmp_path),
        FakeGateway([]),
        resume="latest",
        input_fn=lambda _: "/exit",
        output=lambda _: None,
    )
    assert shell.dialogue.dialogue_id == book.dialogue_id
    assert [item.dialogue_id for item in store.list_recent()] == [book.dialogue_id]
