"""Terminal presentation helpers; no agent control state lives here."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .engine import AgentEvent, AgentResult, EventKind


class TerminalUI:
    """A Rich renderer driven by Engine events, not a second control loop."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(highlight=False)
        self._model_status: Any | None = None

    def banner(
        self,
        *,
        version: str,
        workspace: Path,
        model: str,
        approvals: str,
        dialogue_id: str | None = None,
    ) -> None:
        lines = [
            f"[bold]Workspace[/bold]  {escape(str(workspace))}",
            f"[bold]Model[/bold]      {escape(model)}",
            f"[bold]Approval[/bold]   {escape(approvals)}",
        ]
        if dialogue_id:
            lines.append(f"[bold]Dialogue[/bold]   {escape(dialogue_id)}")
        self.console.print(
            Panel("\n".join(lines), title=f"EvidenceCoder {version}", border_style="cyan")
        )

    def on_event(self, event: AgentEvent) -> None:
        if event.kind is EventKind.MODEL_START:
            self._stop_status()
            self._model_status = self.console.status(
                f"[cyan]Cycle {event.cycle} · waiting for model...[/cyan]", spinner="dots"
            )
            self._model_status.start()
            return
        if event.kind is EventKind.MODEL_END:
            self._stop_status()
            elapsed = event.elapsed_seconds or 0.0
            if event.status == "error":
                self.console.print(f"[red]x[/red] model request failed after {elapsed:.1f}s")
            else:
                self.console.print(f"[dim]Cycle {event.cycle} · model replied in {elapsed:.1f}s[/dim]")
            return
        if event.kind is EventKind.ASSISTANT:
            self.console.print(Panel(Text(event.message), title="Assistant", border_style="blue"))
            return
        if event.kind is EventKind.TOOL_RESULT:
            self._tool_event(event)

    def show_approval(
        self,
        tool: str,
        arguments: dict[str, Any],
        reason: str,
        workspace: Path,
    ) -> None:
        self.console.print(f"\n[yellow bold]! Approval required[/yellow bold] · {tool} · {reason}")
        preview = build_diff_preview(workspace, tool, arguments)
        if preview:
            self.console.print(Syntax(preview, "diff", theme="ansi_dark", word_wrap=True))
            extras = {
                key: value
                for key, value in arguments.items()
                if key not in {"content", "old_text", "new_text"}
            }
            if extras:
                self.console.print(Syntax(json.dumps(extras, ensure_ascii=False, indent=2), "json"))
        else:
            self.console.print(Syntax(json.dumps(arguments, ensure_ascii=False, indent=2), "json"))

    def show_result(self, result: AgentResult) -> None:
        self._stop_status()
        status_color = "green" if result.status.value == "completed" else "red"
        lines = [
            f"[bold]Status:[/bold] [{status_color}]{result.status.value}[/{status_color}]",
            escape(result.summary),
        ]
        completion = result.completion or {}
        if completion.get("changed_files"):
            lines.append(
                "[bold]Changed:[/bold] "
                + escape(", ".join(str(item) for item in completion["changed_files"]))
            )
        if completion.get("checks"):
            lines.append(
                "[bold]Checks:[/bold] "
                + escape(", ".join(str(item) for item in completion["checks"]))
            )
        if completion.get("limitations"):
            lines.append(
                "[bold]Limitations:[/bold] "
                + escape("; ".join(str(item) for item in completion["limitations"]))
            )
        usage = result.runbook
        token_text = (
            f"{usage.prompt_tokens} in / {usage.completion_tokens} out"
            if usage.usage_reports
            else "not reported by gateway"
        )
        lines.append(
            f"[bold]Stats:[/bold] {usage.model_calls} model call(s), "
            f"{len(usage.operations)} tool call(s), {result.duration_seconds:.1f}s, tokens: {token_text}"
        )
        if result.log_path:
            lines.append(f"[bold]Run log:[/bold] {escape(result.log_path)}")
        self.console.print(Panel("\n".join(lines), title="Task result", border_style=status_color))

    def show_history(self, entries: Iterable[Any]) -> None:
        entries = list(entries)
        if not entries:
            self.console.print("[dim][no tasks in this dialogue][/dim]")
            return
        table = Table(title="Dialogue history", show_lines=False)
        table.add_column("#", justify="right", style="dim")
        table.add_column("Status")
        table.add_column("Instruction")
        table.add_column("Summary")
        for index, entry in enumerate(entries, start=1):
            color = "green" if entry.status == "completed" else "yellow"
            table.add_row(
                str(index),
                f"[{color}]{entry.status}[/{color}]",
                Text(entry.instruction),
                Text(entry.summary),
            )
        self.console.print(table)

    def show_resume_choices(self, dialogues: Iterable[Any]) -> None:
        table = Table(title="Resume dialogue", show_lines=False)
        table.add_column("#", justify="right", style="bold cyan")
        table.add_column("Updated")
        table.add_column("Tasks", justify="right")
        table.add_column("Status")
        table.add_column("Latest context")
        for index, dialogue in enumerate(dialogues, start=1):
            latest = dialogue.entries[-1] if dialogue.entries else None
            status = latest.status if latest else "empty"
            context = latest.instruction if latest else "[empty dialogue]"
            if len(context) > 72:
                context = context[:69] + "..."
            table.add_row(
                str(index),
                dialogue.updated_at.replace("T", " ")[:19],
                str(len(dialogue.entries)),
                status,
                Text(context),
            )
        self.console.print(table)

    def show_status(self, lines: dict[str, str]) -> None:
        table = Table(title="EvidenceCoder status", show_header=False)
        table.add_column("Field", style="bold cyan")
        table.add_column("Value")
        for key, value in lines.items():
            table.add_row(key, Text(value))
        self.console.print(table)

    def message(self, message: str, *, style: str | None = None) -> None:
        self.console.print(message, style=style, markup=False)

    def _tool_event(self, event: AgentEvent) -> None:
        status = event.status or ""
        exit_code = (event.evidence or {}).get("exit_code")
        successful = status == "ok" or (status.startswith("executed") and exit_code == 0)
        symbol = "+" if successful else "x"
        color = "green" if successful else ("yellow" if status == "denied" else "red")
        summary = event.message.splitlines()[0] if event.message else ""
        if len(summary) > 120:
            summary = summary[:117] + "..."
        self.console.print(
            f"[{color}]{symbol}[/{color}] [bold]{event.tool}[/bold] "
            f"[dim]{escape(str(event.op_id))}[/dim] · {escape(status)} · {escape(summary)}"
        )

    def _stop_status(self) -> None:
        if self._model_status is not None:
            self._model_status.stop()
            self._model_status = None


def build_diff_preview(
    workspace: Path | str,
    tool: str,
    arguments: dict[str, Any],
    *,
    max_lines: int = 100,
) -> str | None:
    if tool not in {"replace_text", "write_text"}:
        return None
    raw_path = arguments.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    root = Path(workspace).resolve()
    requested = Path(raw_path)
    if requested.is_absolute() or requested.drive:
        return None
    path = (root / requested).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        return None
    try:
        before = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return None
    if tool == "replace_text":
        old = arguments.get("old_text")
        new = arguments.get("new_text")
        count = arguments.get("expected_count", 1)
        if not isinstance(old, str) or not isinstance(new, str) or not isinstance(count, int):
            return None
        after = before.replace(old, new, count)
    else:
        content = arguments.get("content")
        if not isinstance(content, str):
            return None
        after = content
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{raw_path}",
            tofile=f"b/{raw_path}",
            lineterm="",
        )
    )
    if not lines:
        return "[no textual change]"
    if len(lines) > max_lines:
        omitted = len(lines) - max_lines
        lines = lines[:max_lines] + [f"... diff truncated; {omitted} line(s) omitted ..."]
    return "\n".join(lines)


def print_event(event: AgentEvent) -> None:
    if event.kind is EventKind.TOOL_RESULT:
        print(
            f"[EvidenceCoder] {event.op_id} {event.tool}: {event.status} — {event.message}",
            flush=True,
        )
    elif event.kind is EventKind.MODEL_START:
        print(f"[EvidenceCoder] cycle {event.cycle}: asking model", flush=True)
    elif event.kind is EventKind.MODEL_END:
        print(
            f"[EvidenceCoder] cycle {event.cycle}: model replied in "
            f"{(event.elapsed_seconds or 0):.1f}s",
            flush=True,
        )
    elif event.message:
        print(f"[EvidenceCoder] assistant: {event.message}", flush=True)


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
    tokens = (
        f"{result.runbook.prompt_tokens} in / {result.runbook.completion_tokens} out"
        if result.runbook.usage_reports
        else "not reported"
    )
    output(
        f"Stats: {result.runbook.model_calls} model call(s), "
        f"{len(result.runbook.operations)} tool call(s), {result.duration_seconds:.1f}s, "
        f"tokens: {tokens}"
    )
    if result.log_path:
        output(f"Run log: {result.log_path}")
