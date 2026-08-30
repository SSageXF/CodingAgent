"""Platform-side authorization decisions for built-in tools."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


class GuardAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class GuardDecision:
    action: GuardAction
    reason: str


_DANGEROUS_COMMANDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|[;&|])\s*(?:shutdown|reboot|poweroff|halt)\b", re.I), "system power command"),
    (re.compile(r"\b(?:diskpart|mkfs(?:\.[a-z0-9]+)?|format\s+[a-z]:)\b", re.I), "disk formatting command"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "Git hard reset"),
    (re.compile(r"\bgit\s+clean\s+-[^\s]*f", re.I), "Git forced clean"),
    (re.compile(r"\bgit\s+push\b", re.I), "remote Git push"),
    (re.compile(r"\bgit\s+(?:restore\b|checkout\s+--)", re.I), "destructive Git restore"),
    (re.compile(r"\brm\s+-[^\s]*r[^\s]*f[^\r\n]*(?:\s/|\s~|\$HOME)", re.I), "broad recursive deletion"),
    (
        re.compile(r"\brm\s+-[^\s]*(?:rf|fr)[^\r\n]*\s(?:\.|\.\\|\./)(?:\s|$)", re.I),
        "workspace-wide recursive deletion",
    ),
    (
        re.compile(
            r"\bremove-item\b[^\r\n]*-recurse[^\r\n]*(?:\$home|\s~|[a-z]:\\(?:\s|$))",
            re.I,
        ),
        "broad recursive deletion",
    ),
    (
        re.compile(
            r"\bremove-item\b[^\r\n]*-recurse[^\r\n]*\s(?:\.|\.\\|\./)(?:\s|$)",
            re.I,
        ),
        "workspace-wide recursive deletion",
    ),
    (re.compile(r"\b(?:rd|rmdir)\s+/s\b[^\r\n]*[a-z]:\\", re.I), "broad recursive deletion"),
)


class Guard:
    READ_ONLY_TOOLS = {
        "inspect_tree",
        "read_segment",
        "read_many",
        "find_matches",
        "git_status",
        "git_diff",
        "submit_result",
    }
    WRITE_TOOLS = {"replace_text", "write_text"}

    def __init__(
        self,
        *,
        auto_approve_writes: bool = False,
        auto_approve_commands: bool = False,
    ) -> None:
        self.auto_approve_writes = auto_approve_writes
        self.auto_approve_commands = auto_approve_commands

    def assess(self, tool: str, arguments: dict[str, Any]) -> GuardDecision:
        if tool in self.READ_ONLY_TOOLS:
            return GuardDecision(GuardAction.ALLOW, "read-only or internal operation")
        if tool in self.WRITE_TOOLS:
            if self.auto_approve_writes:
                return GuardDecision(GuardAction.ALLOW, "writes were pre-approved for this run")
            return GuardDecision(GuardAction.ASK, "the tool will modify workspace files")
        if tool == "run_local":
            command = str(arguments.get("command", ""))
            for pattern, reason in _DANGEROUS_COMMANDS:
                if pattern.search(command):
                    return GuardDecision(GuardAction.DENY, reason)
            if self.auto_approve_commands:
                return GuardDecision(GuardAction.ALLOW, "commands were pre-approved for this run")
            return GuardDecision(GuardAction.ASK, "the tool will execute a local shell command")
        return GuardDecision(GuardAction.DENY, "unknown tools are never authorized")
