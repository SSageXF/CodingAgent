"""Command-line entry point for EvidenceCoder."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__
from .api_link import APILink
from .display import confirm_tool, print_event
from .engine import Engine, RunStatus
from .settings import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evidencecoder",
        description="Run an evidence-backed coding agent in a local workspace.",
    )
    parser.add_argument("task", nargs="?", help="programming task for the agent")
    parser.add_argument("--workspace", default=".", help="workspace root (default: current directory)")
    parser.add_argument("--model", help="model name; or set EVIDENCECODER_MODEL")
    parser.add_argument("--base-url", help="OpenAI-compatible API base URL")
    parser.add_argument("--api-key", help="API key; environment variables are preferred")
    parser.add_argument("--max-cycles", type=int, help="maximum model cycles")
    parser.add_argument("--wall-time", type=int, help="maximum run time in seconds")
    parser.add_argument("--yes", action="store_true", help="approve ordinary writes and commands")
    parser.add_argument("--yes-writes", action="store_true", help="approve workspace writes")
    parser.add_argument("--yes-commands", action="store_true", help="approve local commands")
    parser.add_argument("--no-save-log", action="store_true", help="do not save the local run log")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    task = args.task
    if not task:
        try:
            task = input("Task: ").strip()
        except EOFError:
            task = ""
    if not task:
        print("error: a task is required", file=sys.stderr)
        return 2

    env_overrides = {
        key: value
        for key, value in {
            "model": args.model,
            "base_url": args.base_url,
            "api_key": args.api_key,
        }.items()
        if value is not None
    }
    try:
        settings = Settings.from_env(Path(args.workspace), **env_overrides)
        changes: dict[str, object] = {
            "auto_approve_writes": args.yes or args.yes_writes,
            "auto_approve_commands": args.yes or args.yes_commands,
            "save_run_log": not args.no_save_log,
        }
        if args.max_cycles is not None:
            changes["max_cycles"] = args.max_cycles
        if args.wall_time is not None:
            changes["wall_time_seconds"] = args.wall_time
        settings = settings.with_overrides(**changes)
        settings.validate()
    except (TypeError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    with APILink(
        base_url=settings.base_url,
        model=settings.model,
        api_key=settings.api_key,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.api_max_retries,
    ) as gateway:
        result = Engine(
            settings,
            gateway,
            approval=confirm_tool,
            observer=print_event,
        ).run(task)

    print(f"\nStatus: {result.status.value}")
    print(result.summary)
    if result.completion:
        changed = result.completion.get("changed_files") or []
        if changed:
            print("Changed files: " + ", ".join(changed))
    if result.log_path:
        print(f"Run log: {result.log_path}")
    return 0 if result.status is RunStatus.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
