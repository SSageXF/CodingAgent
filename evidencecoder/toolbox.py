"""Fixed tool catalog, argument validation, and local dispatch."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Any, Callable

from .completion import CompletionVerifier
from .runbook import OperationStatus, RunBook, ToolOutcome
from .tool_impl import LocalCommands, WorkspaceFiles


class ToolArgumentsError(ValueError):
    pass


class UnknownToolError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any], RunBook], ToolOutcome]

    def api_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Toolbox:
    def __init__(self, workspace: WorkspaceFiles, commands: LocalCommands) -> None:
        self.workspace = workspace
        self.commands = commands
        self.completion = CompletionVerifier()
        self._definitions = self._build_definitions()

    @property
    def api_specs(self) -> list[dict[str, Any]]:
        return [definition.api_spec() for definition in self._definitions.values()]

    def parse_and_validate(self, name: str, arguments_json: str) -> dict[str, Any]:
        definition = self._definitions.get(name)
        if definition is None:
            raise UnknownToolError(f"unknown tool: {name}")
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            raise ToolArgumentsError(f"tool arguments are not valid JSON: {exc.msg}") from exc
        _validate(arguments, definition.parameters, path=name)
        return arguments

    def execute(self, name: str, arguments: dict[str, Any], runbook: RunBook) -> ToolOutcome:
        definition = self._definitions.get(name)
        if definition is None:
            return ToolOutcome(OperationStatus.ERROR, f"unknown tool: {name}", {})
        try:
            return definition.handler(arguments, runbook)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return ToolOutcome(OperationStatus.ERROR, str(exc), {})

    def _build_definitions(self) -> dict[str, ToolDefinition]:
        object_schema = _object_schema
        definitions = [
            ToolDefinition(
                "inspect_tree",
                "List files and directories inside the workspace with explicit depth and entry limits.",
                object_schema(
                    {
                        "path": _string(default="."),
                        "max_depth": _integer(default=3, minimum=0, maximum=10),
                        "max_entries": _integer(default=200, minimum=1, maximum=1000),
                    }
                ),
                lambda args, _: self.workspace.inspect_tree(args),
            ),
            ToolDefinition(
                "read_segment",
                "Read a bounded line range from one UTF-8 text file in the workspace.",
                object_schema(
                    {
                        "path": _string(),
                        "start_line": _integer(default=1, minimum=1, maximum=10_000_000),
                        "end_line": _integer(minimum=1, maximum=10_000_000),
                    },
                    required=["path"],
                ),
                lambda args, _: self.workspace.read_segment(args),
            ),
            ToolDefinition(
                "find_matches",
                "Search workspace text for a literal or regular-expression pattern "
                "using bounded output.",
                object_schema(
                    {
                        "pattern": _string(min_length=1),
                        "path": _string(default="."),
                        "glob": _string(),
                        "max_matches": _integer(default=100, minimum=1, maximum=500),
                    },
                    required=["pattern"],
                ),
                lambda args, _: self.workspace.find_matches(args),
            ),
            ToolDefinition(
                "replace_text",
                "Replace an exact text fragment only when the expected number of matches is found.",
                object_schema(
                    {
                        "path": _string(),
                        "old_text": _string(min_length=1),
                        "new_text": _string(),
                        "expected_count": _integer(default=1, minimum=1, maximum=1000),
                    },
                    required=["path", "old_text", "new_text"],
                ),
                lambda args, _: self.workspace.replace_text(args),
            ),
            ToolDefinition(
                "write_text",
                "Create a UTF-8 text file or explicitly overwrite one inside the workspace.",
                object_schema(
                    {
                        "path": _string(),
                        "content": _string(),
                        "overwrite": _boolean(default=False),
                        "create_parents": _boolean(default=False),
                    },
                    required=["path", "content"],
                ),
                lambda args, _: self.workspace.write_text(args),
            ),
            ToolDefinition(
                "run_local",
                "Run one independent shell command in the workspace and return its "
                "exit code and bounded output.",
                object_schema(
                    {
                        "command": _string(min_length=1),
                        "timeout_seconds": _integer(minimum=1, maximum=300),
                    },
                    required=["command"],
                ),
                lambda args, _: self.commands.run_local(args),
            ),
            ToolDefinition(
                "submit_result",
                "Submit the final result with operation IDs that prove file changes and checks actually occurred.",
                object_schema(
                    {
                        "summary": _string(min_length=1),
                        "changed_files": _array(_string()),
                        "checks": _array(_string()),
                        "evidence_ids": _array(_string(min_length=1), min_items=1),
                        "limitations": _array(_string()),
                    },
                    required=["summary", "changed_files", "checks", "evidence_ids", "limitations"],
                ),
                lambda args, book: self.completion.verify(args, book),
            ),
        ]
        return {definition.name: definition for definition in definitions}

def _validate(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise ToolArgumentsError(f"{path} must be an object")
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise ToolArgumentsError(f"{path} is missing required fields: {', '.join(missing)}")
        properties = schema.get("properties", {})
        extras = sorted(set(value) - set(properties))
        if extras and schema.get("additionalProperties") is False:
            raise ToolArgumentsError(f"{path} has unknown fields: {', '.join(extras)}")
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], path=f"{path}.{key}")
        for key, child_schema in properties.items():
            if key not in value and "default" in child_schema:
                value[key] = child_schema["default"]
        return
    if expected == "string":
        if not isinstance(value, str):
            raise ToolArgumentsError(f"{path} must be a string")
        if len(value) < schema.get("minLength", 0):
            raise ToolArgumentsError(f"{path} is too short")
        return
    if expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ToolArgumentsError(f"{path} must be an integer")
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ToolArgumentsError(f"{path} is outside the allowed range")
        return
    if expected == "boolean":
        if not isinstance(value, bool):
            raise ToolArgumentsError(f"{path} must be a boolean")
        return
    if expected == "array":
        if not isinstance(value, list):
            raise ToolArgumentsError(f"{path} must be an array")
        if len(value) < schema.get("minItems", 0):
            raise ToolArgumentsError(f"{path} does not have enough items")
        for index, item in enumerate(value):
            _validate(item, schema["items"], path=f"{path}[{index}]")
        return
    raise ToolArgumentsError(f"{path} uses an unsupported schema type: {expected}")


def _object_schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _string(*, default: str | None = None, min_length: int = 0) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if default is not None:
        schema["default"] = default
    if min_length:
        schema["minLength"] = min_length
    return schema


def _integer(
    *, default: int | None = None, minimum: int | None = None, maximum: int | None = None
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer"}
    if default is not None:
        schema["default"] = default
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _boolean(*, default: bool | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "boolean"}
    if default is not None:
        schema["default"] = default
    return schema


def _array(items: dict[str, Any], *, min_items: int = 0) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if min_items:
        schema["minItems"] = min_items
    return schema
