"""Small terminal presentation helpers; no agent state lives here."""

from __future__ import annotations

import json
from typing import Any


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
