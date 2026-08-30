from __future__ import annotations

import subprocess

import pytest

from evidencecoder.tool_impl.git_tools import GitTools


def git(tmp_path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_git_status_and_diff_are_read_only_and_bounded(tmp_path):
    git(tmp_path, "init", "-q")
    target = tmp_path / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    git(tmp_path, "add", "sample.py")
    git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "initial",
    )
    target.write_text("value = 2\n", encoding="utf-8")

    tools = GitTools(tmp_path)
    status = tools.status({})
    diff = tools.diff({"path": "sample.py", "staged": False, "max_chars": 12_000})
    assert "sample.py" in status.summary
    assert "-value = 1" in diff.summary
    assert "+value = 2" in diff.summary
    assert diff.evidence == {"path": "sample.py", "staged": False, "truncated": False}


def test_git_diff_rejects_path_escape(tmp_path):
    git(tmp_path, "init", "-q")
    with pytest.raises(ValueError, match="outside"):
        GitTools(tmp_path).diff({"path": "../secret", "max_chars": 12_000})
