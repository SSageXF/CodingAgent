"""Small terminal presentation helpers; no agent state lives here."""

from __future__ import annotations

import json
from typing import Any

from .engine import AgentResult


def print_event(message: str) -> None:
    print(f"[EvidenceCoder] {message}", flush=True)


def confirm_tool(tool: str, arguments: dict[str, Any], reason: str) -> bool:
    print(f"\nApproval required: {tool} ({reason})")
    print(json.dumps(arguments, ensure_ascii=False, indent=2))
    try:
        answer = input("Execute this operation? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def print_agent_result(result: AgentResult, *, output=print) -> None:
    output(f"\nStatus: {result.status.value}")
    output(result.summary)
    if result.completion:
        changed = result.completion.get("changed_files") or []
        checks = result.completion.get("checks") or []
        limitations = result.completion.get("limitations") or []
        if changed:
            output("Changed files: " + ", ".join(changed))
        if checks:
            output("Checks: " + ", ".join(checks))
        if limitations:
            output("Limitations: " + "; ".join(limitations))
    if result.log_path:
        output(f"Run log: {result.log_path}")
