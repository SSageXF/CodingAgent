from __future__ import annotations

import json

import pytest

from evidencecoder.api_link import ModelReply
from evidencecoder.runbook import OperationStatus, RunBook
from evidencecoder.tool_impl import LocalCommands, WorkspaceFiles
from evidencecoder.toolbox import ToolArgumentsError, Toolbox, UnknownToolError


def make_toolbox(tmp_path):
    return Toolbox(WorkspaceFiles(tmp_path), LocalCommands(tmp_path))


def test_schema_rejects_unknown_fields_and_wrong_boolean(tmp_path):
    toolbox = make_toolbox(tmp_path)
    with pytest.raises(ToolArgumentsError, match="unknown fields"):
        toolbox.parse_and_validate("read_segment", '{"path":"x","surprise":1}')
    with pytest.raises(ToolArgumentsError, match="boolean"):
        toolbox.parse_and_validate("write_text", '{"path":"x","content":"","overwrite":1}')
    with pytest.raises(UnknownToolError):
        toolbox.parse_and_validate("not_a_tool", "{}")
    with pytest.raises(ToolArgumentsError, match="too many"):
        toolbox.parse_and_validate(
            "read_many",
            json.dumps({"items": [{"path": "x"}] * 11}),
        )


def test_defaults_are_applied(tmp_path):
    arguments = make_toolbox(tmp_path).parse_and_validate(
        "inspect_tree", "{}"
    )
    assert arguments == {"path": ".", "max_depth": 3, "max_entries": 200}


def test_tool_catalog_contains_ten_fixed_tools(tmp_path):
    names = {item["function"]["name"] for item in make_toolbox(tmp_path).api_specs}
    assert names == {
        "inspect_tree",
        "read_segment",
        "read_many",
        "find_matches",
        "replace_text",
        "write_text",
        "run_local",
        "git_status",
        "git_diff",
        "submit_result",
    }


def test_completion_requires_write_and_successful_check_evidence(tmp_path):
    book = RunBook("fix")
    book.record_assistant(ModelReply("", ()))
    write = book.append_operation(
        tool="write_text",
        arguments={"path": ".github/config"},
        status=OperationStatus.OK,
        summary="written",
        evidence={"path": ".github/config"},
        started_at="now",
        duration_ms=1,
    )
    failed_check = book.append_operation(
        tool="run_local",
        arguments={"command": "pytest"},
        status=OperationStatus.OK,
        summary="exit code: 1",
        evidence={"exit_code": 1},
        started_at="now",
        duration_ms=1,
    )
    toolbox = make_toolbox(tmp_path)
    arguments = {
        "summary": "done",
        "changed_files": ["./.github/config"],
        "checks": ["pytest"],
        "evidence_ids": [write.op_id, failed_check.op_id],
        "limitations": [],
    }
    rejected = toolbox.execute("submit_result", arguments, book)
    assert rejected.status is OperationStatus.ERROR
    assert "exited 0" in rejected.summary

    good_check = book.append_operation(
        tool="run_local",
        arguments={"command": "pytest"},
        status=OperationStatus.OK,
        summary="exit code: 0",
        evidence={"exit_code": 0},
        started_at="now",
        duration_ms=1,
    )
    arguments["evidence_ids"] = [write.op_id, good_check.op_id]
    accepted = toolbox.execute("submit_result", arguments, book)
    assert accepted.status is OperationStatus.OK
    assert accepted.evidence["changed_files"] == [".github/config"]


def test_completion_rejects_check_that_predates_latest_write(tmp_path):
    book = RunBook("fix")
    book.record_assistant(ModelReply("", ()))
    check = book.append_operation(
        tool="run_local",
        arguments={"command": "pytest"},
        status=OperationStatus.OK,
        summary="exit code: 0",
        evidence={"exit_code": 0},
        started_at="now",
        duration_ms=1,
    )
    write = book.append_operation(
        tool="write_text",
        arguments={"path": "x.py"},
        status=OperationStatus.OK,
        summary="written",
        evidence={"path": "x.py"},
        started_at="now",
        duration_ms=1,
    )
    outcome = make_toolbox(tmp_path).execute(
        "submit_result",
        {
            "summary": "done",
            "changed_files": ["x.py"],
            "checks": ["pytest"],
            "evidence_ids": [check.op_id, write.op_id],
            "limitations": [],
        },
        book,
    )
    assert outcome.status is OperationStatus.ERROR
    assert "before the latest" in outcome.summary
