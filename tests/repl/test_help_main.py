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


def test_separators_at_section_boundaries():
    """end_section=True appears on the last row before each non-first section header."""
    entries = list(_HELP_REGISTRY)

    # Collect section header titles that need a divider above them (all but first).
    divider_sections: set[str] = set()
    first_header_seen = False
    for _, cmd, _, desc in entries:
        if cmd is None:
            if first_header_seen:
                divider_sections.add(desc)
            else:
                first_header_seen = True

    table = _build_help_table()
    row_idx = 0
    for i, (_, cmd, arg, desc) in enumerate(entries):
        next_entry = entries[i + 1] if i + 1 < len(entries) else None
        expects_divider = (
            next_entry is not None
            and next_entry[1] is None
            and next_entry[3] in divider_sections
        )
        if cmd is None or cmd == _NOTE:
            row_idx += 1
            continue
        assert table.rows[row_idx].end_section == expects_divider, (
            f"Row {row_idx} (cmd={cmd!r}, arg={arg!r}): "
            f"expected end_section={expects_divider}, "
            f"got {table.rows[row_idx].end_section}"
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


# ---------------------------------------------------------------------------
# test_scan_command_rows_exact
# ---------------------------------------------------------------------------


def test_scan_command_rows_exact():
    """scan command rows: no-arg + --repo= + --tool= + --type= (in order)."""
    scan_args = [arg for _, cmd, arg, _ in _HELP_REGISTRY if cmd == "scan"]
    assert scan_args == [
        None,
        "--repo=<repo>",
        "--tool=<tool,...>",
        "--type=<type,...>",
    ]


# ---------------------------------------------------------------------------
# test_purge_command_rows_exact
# ---------------------------------------------------------------------------


def test_purge_command_rows_exact():
    """purge command rows: no-arg + --tool= (in order)."""
    purge_args = [arg for _, cmd, arg, _ in _HELP_REGISTRY if cmd == "purge"]
    assert purge_args == [None, "--tool=<tool,...>"]


# ---------------------------------------------------------------------------
# test_search_command_rows_exact
# ---------------------------------------------------------------------------


def test_search_command_rows_exact():
    """search command rows: no-arg + all flags in canonical order."""
    search_args = [arg for _, cmd, arg, _ in _HELP_REGISTRY if cmd == "search"]
    assert search_args == [
        None,
        "--tool=<tool,...>",
        "--type=<type,...>",
        "--severity=<level,...>",
        "--<field>=<value>",
        "--<field>~=<value>",
        "--page=<n>",
        "--page-size=<n>",
        "--show-fields",
        "--fields=<f1,f2,...>",
        "--help",
    ]
