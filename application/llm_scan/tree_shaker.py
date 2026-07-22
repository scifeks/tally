"""Directory tree text generation for LLM prompt assembly."""

from __future__ import annotations

from pathlib import Path

DEFAULT_EXCLUDES: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        "target",
        ".env",
        ".idea",
        ".vscode",
        "vendor",
        ".svn",
        "bower_components",
        ".next",
    }
)


def build_tree(
    root: Path,
    max_depth: int = 4,
    exclude_patterns: frozenset[str] | set[str] | None = None,
) -> str:
    """Generate a text representation of the directory tree.

    Args:
        root: The root directory to traverse.
        max_depth: Maximum depth to descend (default 4).
        exclude_patterns: Set of directory/file names to skip. If None,
            uses DEFAULT_EXCLUDES.

    Returns:
        Newline-joined lines showing the tree structure.
    """
    excludes = (
        frozenset(exclude_patterns)
        if exclude_patterns is not None
        else DEFAULT_EXCLUDES
    )
    lines: list[str] = []
    _walk(root, 0, max_depth, excludes, lines)
    return "\n".join(lines)


def _walk(
    current: Path,
    depth: int,
    max_depth: int,
    excludes: frozenset[str],
    lines: list[str],
) -> None:
    """Recursively walk the directory tree and accumulate lines.

    Args:
        current: Current directory being walked.
        depth: Current depth in the tree (0-indexed).
        max_depth: Maximum depth to descend.
        excludes: Set of names to skip.
        lines: Accumulator list for output lines.
    """
    if depth >= max_depth:
        return
    try:
        entries = sorted(
            current.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError:
        return
    indent = "  " * depth
    for entry in entries:
        if entry.name in excludes:
            continue
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            lines.append(f"{indent}{entry.name}/")
            _walk(entry, depth + 1, max_depth, excludes, lines)
        else:
            lines.append(f"{indent}{entry.name}")
