from __future__ import annotations

import sys

from evidencecoder.guard import Guard, GuardAction
from evidencecoder.runbook import OperationStatus
from evidencecoder.tool_impl.commands import LocalCommands, _decode_output


def test_command_records_nonzero_exit_as_observation(tmp_path):
    command = f'"{sys.executable}" -c "raise SystemExit(7)"'
    result = LocalCommands(tmp_path).run_local({"command": command})
    assert result.status is OperationStatus.OK
    assert result.evidence["exit_code"] == 7


def test_command_timeout_is_bounded(tmp_path):
    command = f'"{sys.executable}" -c "import time; time.sleep(3)"'
    result = LocalCommands(tmp_path).run_local({"command": command, "timeout_seconds": 1})
    assert result.status is OperationStatus.TIMEOUT
    assert result.evidence["timeout_seconds"] == 1


def test_guard_denies_destructive_command_even_when_auto_approved():
    guard = Guard(auto_approve_commands=True)
    decision = guard.assess("run_local", {"command": "git reset --hard HEAD~1"})
    assert decision.action is GuardAction.DENY
    assert guard.assess("run_local", {"command": "git push origin main"}).action is GuardAction.DENY
    assert guard.assess("run_local", {"command": "rm -rf ."}).action is GuardAction.DENY


def test_guard_asks_for_write_by_default_and_allows_read():
    guard = Guard()
    assert guard.assess("write_text", {"path": "x"}).action is GuardAction.ASK
    assert guard.assess("read_segment", {"path": "x"}).action is GuardAction.ALLOW


def test_command_output_decoder_handles_utf8_and_gbk():
    utf8, encoding, replaced = _decode_output("测试".encode("utf-8"), ["utf-8", "gbk"])
    assert (utf8, encoding, replaced) == ("测试", "utf-8", False)
    gbk, encoding, replaced = _decode_output("测试".encode("gbk"), ["utf-8", "gbk"])
    assert (gbk, encoding, replaced) == ("测试", "gbk", False)
