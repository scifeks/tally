"""Regression guard: no input() calls below the adapter layer.

Walks application/ and domain/ source trees and fails if any call to
the builtin input() is found outside the explicitly whitelisted paths.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

# Paths (relative to repo root) where input() is permitted.
_ALLOWED_PREFIXES = (
    os.path.join("application", "repl"),
    os.path.join("application", "setup"),
    os.path.join("application", "project", "wizard.py"),
)

_REPO_ROOT = Path(__file__).parent.parent.parent


def _collect_input_call_sites() -> list[tuple[str, int]]:
    violations: list[tuple[str, int]] = []
    for scan_root in ("application", "domain"):
        for py_file in (_REPO_ROOT / scan_root).rglob("*.py"):
            rel = str(py_file.relative_to(_REPO_ROOT))
            if any(rel.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
                continue
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "input"
                ):
                    violations.append((rel, node.lineno))
    return violations


def test_no_input_calls_below_adapter_layer() -> None:
    violations = _collect_input_call_sites()
    if violations:
        lines = "\n".join(f"  {path}:{lineno}" for path, lineno in violations)
        raise AssertionError(
            f"input() found below the adapter layer:\n{lines}\n\n"
            "Move the call into application/repl/ or inject a UserPromptPort."
        )
