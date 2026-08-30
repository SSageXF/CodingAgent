from __future__ import annotations

import pytest

from evidencecoder.runbook import OperationStatus
from evidencecoder.tool_impl.files import FileToolError, WorkspaceFiles


def test_path_traversal_is_rejected(tmp_path):
    files = WorkspaceFiles(tmp_path)
    with pytest.raises(FileToolError, match="outside"):
        files.resolve("../secret.txt", for_write=True)


def test_absolute_path_is_rejected(tmp_path):
    files = WorkspaceFiles(tmp_path)
    with pytest.raises(FileToolError, match="absolute"):
        files.resolve(str(tmp_path / "absolute.txt"), for_write=True)


def test_symlink_escape_is_rejected(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are not available")
    files = WorkspaceFiles(tmp_path)
    with pytest.raises(FileToolError, match="outside"):
        files.resolve("link/escaped.txt", for_write=True)


def test_read_replace_and_write_report_hash_evidence(tmp_path):
    target = tmp_path / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    files = WorkspaceFiles(tmp_path)

    read = files.read_segment({"path": "sample.py", "start_line": 1, "end_line": 2})
    assert read.status is OperationStatus.OK
    assert "value = 1" in read.summary
    assert len(read.evidence["sha256"]) == 64

    replaced = files.replace_text(
        {"path": "sample.py", "old_text": "value = 1", "new_text": "value = 2"}
    )
    assert replaced.evidence["before_sha256"] != replaced.evidence["after_sha256"]
    assert target.read_text(encoding="utf-8") == "value = 2\n"

    written = files.write_text(
        {"path": "nested/new.txt", "content": "hello", "create_parents": True}
    )
    assert written.evidence["created"] is True
    assert (tmp_path / "nested" / "new.txt").read_text(encoding="utf-8") == "hello"


def test_replace_requires_exact_expected_count(tmp_path):
    (tmp_path / "many.txt").write_text("x x", encoding="utf-8")
    files = WorkspaceFiles(tmp_path)
    with pytest.raises(FileToolError, match="expected 1 exact matches but found 2"):
        files.replace_text(
            {"path": "many.txt", "old_text": "x", "new_text": "y", "expected_count": 1}
        )
    assert (tmp_path / "many.txt").read_text(encoding="utf-8") == "x x"


def test_inspect_tree_excludes_runtime_directories(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hidden").write_text("x", encoding="utf-8")
    (tmp_path / "visible.txt").write_text("ok", encoding="utf-8")
    outcome = WorkspaceFiles(tmp_path).inspect_tree(
        {"path": ".", "max_depth": 2, "max_entries": 20}
    )
    assert "visible.txt" in outcome.summary
    assert ".git" not in outcome.summary


def test_read_many_reads_bounded_segments(tmp_path):
    (tmp_path / "one.py").write_text("one = 1\nline = 2\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("two = 2\n", encoding="utf-8")
    outcome = WorkspaceFiles(tmp_path).read_many(
        {
            "items": [
                {"path": "one.py", "start_line": 1, "end_line": 1},
                {"path": "two.py", "start_line": 1, "end_line": 2},
            ]
        }
    )
    assert outcome.status is OperationStatus.OK
    assert "===== one.py =====" in outcome.summary
    assert "one = 1" in outcome.summary
    assert "line = 2" not in outcome.summary
    assert "two = 2" in outcome.summary
    assert outcome.evidence["file_count"] == 2


def test_read_many_rejects_too_many_files(tmp_path):
    files = WorkspaceFiles(tmp_path)
    with pytest.raises(FileToolError, match="at most 10"):
        files.read_many({"items": [{"path": "x"}] * 11})
