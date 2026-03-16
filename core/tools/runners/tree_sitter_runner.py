#!/usr/bin/env python3
"""Tree-sitter structural code extractor — called as subprocess by TreeSitterLocalTool.

Usage:
    python tree_sitter_runner.py <repo_path> [--format json]

Outputs JSON to stdout, exits 0 always.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".php": "php",
    ".rb": "ruby",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "c_sharp",
    ".rs": "rust",
}

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "vendor",
        "__pycache__",
        ".venv",
        "dist",
        "build",
        ".tox",
    }
)

MAX_FILE_BYTES = 1_048_576  # 1 MB

# ---------------------------------------------------------------------------
# Per-language query catalogue
# category -> (query_string, root_capture_name)
# ---------------------------------------------------------------------------

_PYTHON_QUERIES: dict[str, tuple[str, str]] = {
    "functions": (
        "(function_definition"
        " name: (identifier) @name"
        " parameters: (parameters) @params) @func",
        "func",
    ),
    "classes": (
        "(class_definition name: (identifier) @name) @cls",
        "cls",
    ),
    "imports": (
        "[(import_statement) (import_from_statement)] @imp",
        "imp",
    ),
    "calls": (
        "(call function: (_) @callee) @call",
        "call",
    ),
    "assignments": (
        "(assignment left: (identifier) @name) @assign",
        "assign",
    ),
}

_JS_QUERIES: dict[str, tuple[str, str]] = {
    "functions": (
        "[(function_declaration"
        "   name: (identifier) @name"
        "   parameters: (formal_parameters) @params)"
        " (method_definition"
        "   name: (property_identifier) @name"
        "   parameters: (formal_parameters) @params)] @func",
        "func",
    ),
    "classes": (
        "(class_declaration name: (identifier) @name) @cls",
        "cls",
    ),
    "imports": (
        "(import_statement) @imp",
        "imp",
    ),
    "calls": (
        "(call_expression function: (_) @callee) @call",
        "call",
    ),
    "assignments": (
        "(variable_declarator name: (identifier) @name) @decl",
        "decl",
    ),
}

_PHP_QUERIES: dict[str, tuple[str, str]] = {
    "functions": (
        "[(function_definition name: (name) @name)"
        " (method_declaration name: (name) @name)] @func",
        "func",
    ),
    "classes": (
        "(class_declaration name: (name) @name) @cls",
        "cls",
    ),
    "imports": (
        "(use_declaration) @imp",
        "imp",
    ),
    "calls": (
        "(function_call_expression function: (name) @callee) @call",
        "call",
    ),
}

QUERIES_BY_LANGUAGE: dict[str, dict[str, tuple[str, str]]] = {
    "python": _PYTHON_QUERIES,
    "javascript": _JS_QUERIES,
    "typescript": _JS_QUERIES,
    "tsx": _JS_QUERIES,
    "php": _PHP_QUERIES,
}


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _node_text(node: object) -> str:
    raw: bytes = getattr(node, "text", None) or b""
    return raw.decode("utf-8", errors="replace")


def _start_line(node: object) -> int:
    pt = getattr(node, "start_point", (0, 0))
    return pt[0] + 1


def _end_line(node: object) -> int:
    pt = getattr(node, "end_point", (0, 0))
    return pt[0] + 1


def _first_node(capture_dict: dict[str, Any], name: str) -> object | None:
    val = capture_dict.get(name)
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _extract_functions(
    matches: list[tuple[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for _, cap in matches:
        root = _first_node(cap, "func")
        if root is None:
            continue
        name_node = _first_node(cap, "name")
        params_node = _first_node(cap, "params")
        name = _node_text(name_node) if name_node else ""
        params = _node_text(params_node)[:120] if params_node else ""
        results.append(
            {
                "name": name,
                "start_line": _start_line(root),
                "end_line": _end_line(root),
                "parameters": params,
            }
        )
    return results


def _extract_classes(
    matches: list[tuple[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for _, cap in matches:
        root = _first_node(cap, "cls")
        if root is None:
            continue
        name_node = _first_node(cap, "name")
        name = _node_text(name_node) if name_node else ""
        results.append(
            {
                "name": name,
                "start_line": _start_line(root),
                "end_line": _end_line(root),
            }
        )
    return results


def _extract_imports(
    matches: list[tuple[int, dict[str, Any]]],
) -> list[str]:
    results: list[str] = []
    for _, cap in matches:
        node = _first_node(cap, "imp")
        if node is None:
            continue
        text = _node_text(node)
        first_line = text.splitlines()[0] if text else ""
        if first_line:
            results.append(first_line)
    return results


def _extract_calls(
    matches: list[tuple[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    results: list[dict[str, Any]] = []
    for _, cap in matches:
        callee_node = _first_node(cap, "callee")
        root = _first_node(cap, "call")
        if callee_node is None or root is None:
            continue
        callee = _node_text(callee_node)[:80]
        line = _start_line(root)
        key = (callee, line)
        if key in seen:
            continue
        seen.add(key)
        results.append({"callee": callee, "line": line})
    return results


def _extract_assignments(
    matches: list[tuple[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for _, cap in matches:
        name_node = _first_node(cap, "name")
        root = _first_node(cap, "assign") or _first_node(cap, "decl")
        if name_node is None:
            continue
        name = _node_text(name_node)
        if name.startswith("_"):
            continue
        line = _start_line(root) if root else _start_line(name_node)
        results.append({"name": name, "line": line})
    return results


# ---------------------------------------------------------------------------
# Per-file extraction
# ---------------------------------------------------------------------------


def _extract_file(
    file_path: Path,
    lang_name: str,
    repo_path: Path,
) -> dict[str, Any]:
    """Parse one file and return a file record dict."""
    try:
        rel_path = str(file_path.relative_to(repo_path))
    except ValueError:
        rel_path = str(file_path)

    base_record: dict[str, Any] = {
        "file_path": rel_path,
        "language": lang_name,
        "functions": [],
        "classes": [],
        "imports": [],
        "calls": [],
        "assignments": [],
    }

    queries = QUERIES_BY_LANGUAGE.get(lang_name)
    if not queries:
        return base_record

    try:
        source_bytes = file_path.read_bytes()
    except OSError:
        return base_record

    try:
        from tree_sitter import Query, QueryCursor
        from tree_sitter_language_pack import get_language, get_parser
    except ImportError:
        return base_record

    try:
        lang = get_language(lang_name)  # type: ignore[arg-type]
        parser = get_parser(lang_name)  # type: ignore[arg-type]
        tree = parser.parse(source_bytes)
    except Exception as exc:
        print(
            f"tree_sitter_runner: language {lang_name!r} unavailable: {exc}",
            file=sys.stderr,
        )
        return base_record

    def _run_query(
        pattern: str,
    ) -> list[tuple[int, dict[str, Any]]]:
        try:
            q = Query(lang, pattern)
            cursor = QueryCursor(q)  # type: ignore[arg-type]
            return list(cursor.matches(tree.root_node))
        except Exception:
            return []

    record = dict(base_record)

    funcs_q, _ = queries["functions"]
    record["functions"] = _extract_functions(_run_query(funcs_q))

    cls_q, _ = queries["classes"]
    record["classes"] = _extract_classes(_run_query(cls_q))

    imp_q, _ = queries["imports"]
    record["imports"] = _extract_imports(_run_query(imp_q))

    calls_q, _ = queries["calls"]
    record["calls"] = _extract_calls(_run_query(calls_q))

    if "assignments" in queries:
        assign_q, _ = queries["assignments"]
        record["assignments"] = _extract_assignments(_run_query(assign_q))

    return record


# ---------------------------------------------------------------------------
# Repository walk
# ---------------------------------------------------------------------------


def _walk_repo(repo_path: Path) -> list[tuple[Path, str]]:
    results: list[tuple[Path, str]] = []
    for dirpath, dirnames, filenames in repo_path.walk():
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for fname in filenames:
            fpath = dirpath / fname
            lang = EXTENSION_MAP.get(fpath.suffix)
            if lang is None:
                continue
            try:
                if fpath.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            results.append((fpath, lang))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="tree-sitter structural code extractor"
    )
    parser.add_argument("repo_path", help="Path to the repository to scan")
    parser.add_argument(
        "--format",
        choices=["json"],
        default="json",
        help="Output format (default: json)",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.is_dir():
        output = {
            "error": f"repo_path is not a directory: {repo_path}",
            "files": [],
            "summary": {
                "total_files": 0,
                "languages_detected": [],
            },
        }
        print(json.dumps(output))
        return

    files = _walk_repo(repo_path)
    file_records: list[dict[str, Any]] = []
    languages_seen: set[str] = set()

    for file_path, lang_name in files:
        record = _extract_file(file_path, lang_name, repo_path)
        file_records.append(record)
        languages_seen.add(lang_name)

    output = {
        "files": file_records,
        "summary": {
            "total_files": len(file_records),
            "languages_detected": sorted(languages_seen),
        },
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
