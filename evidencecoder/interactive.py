"""A small line-oriented interface around independent Engine runs."""

from __future__ import annotations

import json
from typing import Any, Callable

from . import __version__
from .dialogue import DialogueBook, DialogueError, DialogueStore
from .display import print_agent_result
from .engine import Engine
from .settings import Settings


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]


class ApprovalManager:
    def __init__(self, input_fn: InputFunction = input, output: OutputFunction = print) -> None:
        self.input = input_fn
        self.output = output
        self.approved_categories: set[str] = set()

    def __call__(self, tool: str, arguments: dict[str, Any], reason: str) -> bool:
        category = "command" if tool == "run_local" else "write"
        if category in self.approved_categories:
            return True
        self.output(f"\nApproval required: {tool} ({reason})")
        self.output(json.dumps(arguments, ensure_ascii=False, indent=2))
        while True:
            try:
                answer = self.input("Execute? [y]es/[n]o/[a]ll this type/[q]uit task: ").strip().lower()
            except EOFError:
                return False
            if answer in {"y", "yes"}:
                return True
            if answer in {"", "n", "no"}:
                return False
            if answer in {"a", "all"}:
                self.approved_categories.add(category)
                return True
            if answer in {"q", "quit"}:
                raise KeyboardInterrupt
            self.output("Please enter y, n, a, or q.")


class InteractiveShell:
    def __init__(
        self,
        settings: Settings,
        gateway: Any,
        *,
        resume: str | None = None,
        input_fn: InputFunction = input,
        output: OutputFunction = print,
    ) -> None:
        self.settings = settings
        self.gateway = gateway
        self.input = input_fn
        self.output = output
        self.store = DialogueStore(settings.workspace)
        self.dialogue = self.store.load(resume) if resume else DialogueBook.create(settings.workspace)
        self.approval = ApprovalManager(input_fn, output)

    def run(self) -> int:
        self._banner()
        interrupted_input = False
        while True:
            try:
                raw = self.input("evidencecoder> ")
            except EOFError:
                self.output("")
                return 0
            except KeyboardInterrupt:
                if interrupted_input:
                    self.output("\nExiting.")
                    return 0
                self.output("\nInput cleared. Use Ctrl+C again or /exit to leave.")
                interrupted_input = True
                continue
            interrupted_input = False
            instruction = raw.strip()
            if not instruction:
                continue
            if instruction.startswith("/"):
                try:
                    should_exit = self._command(instruction)
                except KeyboardInterrupt:
                    self.output("\nPaste cancelled.")
                    continue
                if should_exit:
                    return 0
                continue
            self._run_instruction(instruction)

    def _run_instruction(self, instruction: str) -> None:
        engine = Engine(
            self.settings,
            self.gateway,
            approval=self.approval,
            observer=self._event,
        )
        result = engine.run(instruction, prior_context=self.dialogue.project())
        self.dialogue.append_result(instruction, result)
        self.store.save(self.dialogue)
        print_agent_result(result, output=self.output)

    def _command(self, raw: str) -> bool:
        command, _, argument = raw.partition(" ")
        command = command.lower()
        argument = argument.strip()
        if command in {"/exit", "/quit"}:
            return True
        if command == "/help":
            self.output(
                "/help  /status  /history  /new  /resume <id|latest>  "
                "/paste  /exit\n"
                "approval: y=once, n=deny, a=allow this type for this process, q=cancel task"
            )
            return False
        if command == "/status":
            status = (
                f"workspace={self.settings.workspace}\nmodel={self.settings.model}\n"
                f"dialogue={self.dialogue.dialogue_id}\ntasks={len(self.dialogue.entries)}"
            )
            if self.dialogue.entries:
                latest = self.dialogue.entries[-1]
                status += f"\nlatest=[{latest.status}] {latest.summary}"
            self.output(status)
            return False
        if command == "/history":
            if not self.dialogue.entries:
                self.output("[no tasks in this dialogue]")
            for index, entry in enumerate(self.dialogue.entries, start=1):
                self.output(f"{index}. [{entry.status}] {entry.instruction} — {entry.summary}")
            return False
        if command == "/new":
            self.dialogue = DialogueBook.create(self.settings.workspace)
            self.store.save(self.dialogue)
            self.output(f"new dialogue: {self.dialogue.dialogue_id} (workspace files unchanged)")
            return False
        if command == "/resume":
            if not argument:
                self.output("usage: /resume <dialogue-id|latest>")
                return False
            try:
                self.dialogue = self.store.load(argument)
            except DialogueError as exc:
                self.output(f"resume failed: {exc}")
            else:
                self.output(
                    f"resumed dialogue {self.dialogue.dialogue_id} "
                    f"with {len(self.dialogue.entries)} task(s)"
                )
            return False
        if command == "/paste":
            lines: list[str] = []
            self.output("Paste task text; enter /end on its own line to run it.")
            while True:
                try:
                    line = self.input("... ")
                except EOFError:
                    break
                if line.strip().lower() == "/end":
                    break
                lines.append(line)
            instruction = "\n".join(lines).strip()
            if instruction:
                self._run_instruction(instruction)
            return False
        self.output(f"unknown command: {command}; use /help")
        return False

    def _banner(self) -> None:
        approvals = "pre-approved" if (
            self.settings.auto_approve_writes and self.settings.auto_approve_commands
        ) else "ask"
        self.output(
            f"EvidenceCoder {__version__} interactive\nworkspace: {self.settings.workspace}\n"
            f"model: {self.settings.model}\napprovals: {approvals}\n"
            f"dialogue: {self.dialogue.dialogue_id}\ntype /help for commands"
        )

    def _event(self, message: str) -> None:
        self.output(f"[EvidenceCoder] {message}")
