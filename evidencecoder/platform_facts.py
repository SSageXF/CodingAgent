"""Small, non-secret platform facts that help the model choose valid commands."""

from __future__ import annotations

import os
import platform
import shlex
import sys
from typing import Any


def collect_platform_facts() -> dict[str, Any]:
    """Return command-relevant facts without copying the process environment."""

    if os.name == "nt":
        shell = "cmd.exe"
        python_command = _quote_windows(sys.executable)
        command_hint = "Use Windows cmd.exe syntax; do not use cat, rm, or python3."
    else:
        shell = os.path.basename(os.environ.get("SHELL", "/bin/sh"))
        python_command = shlex.quote(sys.executable)
        command_hint = "Use POSIX shell syntax."
    return {
        "operating_system": platform.system() or os.name,
        "shell": shell,
        "path_separator": os.sep,
        "recommended_python_command": python_command,
        "command_hint": command_hint,
    }


def _quote_windows(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'
