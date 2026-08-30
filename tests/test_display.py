from __future__ import annotations

from io import StringIO

from rich.console import Console

from evidencecoder.display import TerminalUI, build_diff_preview
from evidencecoder.engine import AgentResult, RunStatus
from evidencecoder.runbook import RunBook


def test_diff_preview_shows_exact_file_change(tmp_path):
    (tmp_path / "sample.py").write_text("value = 1\n", encoding="utf-8")
    preview = build_diff_preview(
        tmp_path,
        "replace_text",
        {"path": "sample.py", "old_text": "value = 1", "new_text": "value = 2"},
    )
    assert preview is not None
    assert "-value = 1" in preview
    assert "+value = 2" in preview


def test_rich_result_contains_status_and_usage():
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None, width=100)
    book = RunBook("task")
    book.model_calls = 2
    book.prompt_tokens = 10
    book.completion_tokens = 3
    book.usage_reports = 2
    result = AgentResult(RunStatus.COMPLETED, "done", book, duration_seconds=1.25)
    TerminalUI(console).show_result(result)
    rendered = stream.getvalue()
    assert "Status: completed" in rendered
    assert "2 model call(s)" in rendered
    assert "10 in / 3 out" in rendered
