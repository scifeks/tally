"""Tests for the 3-column main help table (_build_help_table)."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.table import Table

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.repl.interface import _HELP_REGISTRY, _NOTE, REPL  # noqa: E402


def _render(table: Table) -> str:
    buf = StringIO()
    con = Console(file=buf, markup=False, highlight=False, width=200)
    con.print(table)
    return buf.getvalue()


def _build_help_table(group: str | None = None) -> Table:
    """Call REPL._build_help_table without a live REPL instance."""
    from unittest.mock import MagicMock

    repl = MagicMock(spec=REPL)
    return REPL._build_help_table(repl, group=group)


# ---------------------------------------------------------------------------
# test_help_table_has_three_columns
# ---------------------------------------------------------------------------


def test_help_table_has_three_columns():
    table = _build_help_table()
    assert len(table.columns) == 3


# ---------------------------------------------------------------------------
# test_each_command_appears_once_in_command_column
# ---------------------------------------------------------------------------


def test_each_command_appears_once_in_command_column():
    """No command label should appear in more than one non-consecutive run."""
    cmds = [cmd for _, cmd, _, _ in _HELP_REGISTRY if cmd is not None and cmd != _NOTE]
    # Build runs: consecutive equal values are one run
    prev = object()
    run_starts: list[str] = []
    for c in cmds:
        if c != prev:
            run_starts.append(c)
            prev = c
    # Each command should appear as exactly one run
    seen: set[str] = set()
    for c in run_starts:
        assert c not in seen, f"Command {c!r} appears in multiple non-consecutive runs"
        seen.add(c)


# ---------------------------------------------------------------------------
# test_separators_only_for_multi_row_commands
# ---------------------------------------------------------------------------


def test_separators_only_for_multi_row_commands():
    from collections import Counter

    entries = list(_HELP_REGISTRY)
    cmd_counts: Counter[str] = Counter(
        cmd for _, cmd, _, _ in entries if cmd is not None and cmd != _NOTE
    )
    last_row_idx: dict[str, int] = {}
    for i, (_, cmd, _, _) in enumerate(entries):
        if cmd is not None and cmd != _NOTE:
            last_row_idx[cmd] = i

    # Build the table and verify end_section alignment
    table = _build_help_table()
    # Map table rows back to registry entries (skip group-filtered rows = none here)
    row_idx = 0
    for i, (_, cmd, _, _) in enumerate(entries):
        if cmd is None or cmd == _NOTE:
            row_idx += 1
            continue
        is_last = last_row_idx[cmd] == i
        expected_end_sec = is_last and cmd_counts[cmd] > 1
        assert table.rows[row_idx].end_section == expected_end_sec, (
            f"Row {row_idx} (cmd={cmd!r}): expected end_section="
            f"{expected_end_sec}, got {table.rows[row_idx].end_section}"
        )
        row_idx += 1


# ---------------------------------------------------------------------------
# test_no_filter_keys_text
# ---------------------------------------------------------------------------


def test_no_filter_keys_text():
    rendered = _render(_build_help_table())
    assert "Filter keys" not in rendered
    assert "Filter Keys" not in rendered


# ---------------------------------------------------------------------------
# test_no_arg_syntax_in_command_column
# ---------------------------------------------------------------------------


def test_no_arg_syntax_in_command_column():
    for _, cmd, _, _ in _HELP_REGISTRY:
        if cmd is None or cmd == _NOTE:
            continue
        assert "<" not in cmd, (
            f"Command column entry {cmd!r} contains '<'; move to Arguments column"
        )
        assert "[" not in cmd, (
            f"Command column entry {cmd!r} contains '['; move to Arguments column"
        )
