"""Parser for tree-sitter runner JSON output."""

import json
from pathlib import Path
from typing import Any


def parse_tree_sitter_json(json_path: Path) -> dict[str, Any]:
    """Parse a tree-sitter JSON output file into structured data."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return _error_result(f"JSON parse error: {exc}")
    return _parse_tree_sitter_data(data)


def parse_tree_sitter_json_string(json_string: str) -> dict[str, Any]:
    """Parse tree-sitter JSON from a raw string into structured data."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return _error_result(f"JSON parse error: {exc}")
    return _parse_tree_sitter_data(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _error_result(message: str) -> dict[str, Any]:
    return {
        "error": message,
        "files": [],
        "summary": {
            "total_files": 0,
            "languages_detected": [],
        },
    }


def _parse_tree_sitter_data(data: dict[str, Any]) -> dict[str, Any]:
    files = [_parse_file_record(f) for f in data.get("files", [])]
    raw = data.get("summary", {})
    return {
        "files": files,
        "summary": {
            "total_files": raw.get("total_files", len(files)),
            "languages_detected": raw.get("languages_detected", []),
        },
    }


def _parse_file_record(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_path": f.get("file_path", ""),
        "language": f.get("language", ""),
        "functions": f.get("functions", []),
        "classes": f.get("classes", []),
        "imports": f.get("imports", []),
        "calls": f.get("calls", []),
        "assignments": f.get("assignments", []),
    }
