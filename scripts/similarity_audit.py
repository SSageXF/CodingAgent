"""Screen EvidenceCoder modules against checked-out reference repositories.

This is a candidate finder, not a plagiarism detector. It combines normalized
line runs, token 5-gram Jaccard similarity, and Python AST node histograms so
that every threshold hit can be reviewed manually.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable


SOURCE_SUFFIXES = {".py", ".rs", ".ts", ".tsx", ".js", ".jsx"}
SKIP_PARTS = {
    ".git",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    ".venv",
    "__pycache__",
    "fixtures",
    "snapshots",
}
TOKEN_RE = re.compile(
    r"[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?|==|!=|<=|>=|->|=>|::|&&|\|\||[^\s]"
)


@dataclass(frozen=True)
class Candidate:
    own_file: str
    reference_file: str
    score: float


def source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower() in SOURCE_SUFFIXES
            and path.stat().st_size <= 1_000_000
            and not any(part in SKIP_PARTS for part in path.parts)
        ):
            yield path


def normalized_tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def grams(tokens: list[str], size: int = 5) -> set[int]:
    if len(tokens) < size:
        return set()
    return {
        int.from_bytes(
            hashlib.blake2b("\0".join(tokens[index : index + size]).encode(), digest_size=8).digest(),
            "big",
        )
        for index in range(len(tokens) - size + 1)
    }


def jaccard(left: set[int], right: set[int]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def normalized_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        compact = " ".join(line.strip().split())
        if compact and not compact.startswith(("#", "//", "/*", "*")):
            lines.append(compact)
    return lines


def line_run_hashes(lines: list[str], size: int = 10) -> set[str]:
    return {
        hashlib.sha256("\n".join(lines[index : index + size]).encode()).hexdigest()
        for index in range(max(0, len(lines) - size + 1))
    }


def function_shapes(path: Path, text: str) -> list[tuple[str, set[int]]]:
    if path.suffix != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    shapes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            statement_count = sum(isinstance(item, ast.stmt) for item in ast.walk(node))
            if statement_count >= 20:
                sequence = _ast_sequence(node)
                shapes.append((node.name, grams(sequence, size=4)))
    return shapes


def _ast_sequence(node: ast.AST) -> list[str]:
    """Preorder node/field sequence with names and literals deliberately erased."""

    sequence: list[str] = []

    def visit(current: ast.AST) -> None:
        sequence.append(type(current).__name__)
        for field, value in ast.iter_fields(current):
            if field in {"name", "id", "arg", "attr", "value", "kind", "type_comment"}:
                continue
            sequence.append(f"field:{field}")
            if isinstance(value, ast.AST):
                visit(value)
            elif isinstance(value, list):
                sequence.append("list")
                for item in value:
                    if isinstance(item, ast.AST):
                        visit(item)
                sequence.append("endlist")
        sequence.append(f"end:{type(current).__name__}")

    visit(node)
    return sequence


def scan(own_root: Path, reference_roots: list[Path]) -> dict[str, object]:
    own_data = _load(own_root)
    reference_data = []
    for root in reference_roots:
        reference_data.extend(_load(root, label=root.name))

    lexical: list[Candidate] = []
    exact_runs: list[dict[str, str]] = []
    ast_candidates: list[dict[str, object]] = []
    reference_line_index: dict[str, list[str]] = defaultdict(list)
    for item in reference_data:
        for digest in item["line_hashes"]:
            reference_line_index[digest].append(item["display"])

    for own in own_data:
        for reference in reference_data:
            score = jaccard(own["grams"], reference["grams"])
            if score >= 0.10:
                lexical.append(Candidate(own["display"], reference["display"], score))
        matches: set[str] = set()
        for digest in own["line_hashes"]:
            matches.update(reference_line_index.get(digest, ()))
        for matched in sorted(matches):
            exact_runs.append({"own_file": own["display"], "reference_file": matched})

        for own_name, own_shape in own["shapes"]:
            best: tuple[float, str, str] = (0.0, "", "")
            for reference in reference_data:
                for reference_name, reference_shape in reference["shapes"]:
                    score = jaccard(own_shape, reference_shape)
                    if score > best[0]:
                        best = (score, reference["display"], reference_name)
            if best[0] >= 0.80:
                ast_candidates.append(
                    {
                        "own_file": own["display"],
                        "own_function": own_name,
                        "reference_file": best[1],
                        "reference_function": best[2],
                        "structure_4gram_jaccard": round(best[0], 4),
                    }
                )

    lexical.sort(key=lambda item: item.score, reverse=True)
    per_module: dict[str, Candidate] = {}
    for item in lexical:
        per_module.setdefault(item.own_file, item)
    return {
        "method": {
            "source_suffixes": sorted(SOURCE_SUFFIXES),
            "token_gram_size": 5,
            "lexical_candidate_threshold": 0.10,
            "manual_review_threshold": 0.30,
            "red_line_threshold": 0.45,
            "exact_nonblank_line_run": 10,
            "python_ast_structure_4gram_threshold": 0.80,
            "python_ast_minimum_statement_nodes": 20,
        },
        "counts": {"own_files": len(own_data), "reference_files": len(reference_data)},
        "highest_lexical_candidate_per_module": [
            asdict(item) | {"score": round(item.score, 4)} for item in per_module.values()
        ],
        "lexical_threshold_hits_0_30": [
            asdict(item) | {"score": round(item.score, 4)}
            for item in lexical
            if item.score >= 0.30
        ],
        "exact_10_line_hits": exact_runs,
        "python_ast_candidates": ast_candidates,
    }


def _load(root: Path, label: str | None = None) -> list[dict[str, object]]:
    loaded = []
    for path in source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        tokens = normalized_tokens(text)
        display = (
            f"{label}/{path.relative_to(root).as_posix()}"
            if label
            else path.relative_to(root).as_posix()
        )
        loaded.append(
            {
                "display": display,
                "grams": grams(tokens),
                "line_hashes": line_run_hashes(normalized_lines(text)),
                "shapes": function_shapes(path, text),
            }
        )
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--own", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = scan(args.own.resolve(), [path.resolve() for path in args.reference])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
