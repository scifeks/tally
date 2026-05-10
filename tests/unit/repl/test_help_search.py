"""Tests for `help search` subcommand and _build_search_help_table."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console
from rich.table import Table

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.repl.interface import _build_search_help_table  # noqa: E402


def _render(table: Table) -> str:
    buf = StringIO()
    con = Console(file=buf, markup=False, highlight=False, width=200)
    con.print(table)
    return buf.getvalue()


# _build_search_help_table: no tool (full table)


def test_help_search_full_shows_all_domains():
    rendered = _render(_build_search_help_table())
    assert "Code Domain" in rendered
    assert "Web Domain" in rendered


def test_help_search_full_does_not_show_project_management():
    rendered = _render(_build_search_help_table())
    assert "Project Management" not in rendered


# _build_search_help_table: gitleaks (code domain)


def test_help_search_gitleaks_shows_code_keys():
    rendered = _render(_build_search_help_table("gitleaks"))
    assert "Code Domain" in rendered
    assert "file" in rendered
    assert "rule" in rendered


# _build_search_help_table: zap (web domain)


def test_help_search_zap_shows_web_keys():
    rendered = _render(_build_search_help_table("zap"))
    assert "Web Domain" in rendered
    assert "url" in rendered
    assert "method" in rendered
    assert "param" in rendered
    assert "alert" in rendered


# _cmd_help_search: unknown tool


def test_cmd_help_search_unknown_tool_prints_error():
    from application.repl.interface import REPL

    repl = MagicMock(spec=REPL)
    repl.config = MagicMock()
    repl.config.load_commands_config.return_value = {}
    repl.console = MagicMock()

    # Call the unbound method with our mock repl as self
    REPL._cmd_help_search(repl, ["unknowntool"])

    printed_args = [str(call) for call in repl.console.print.call_args_list]
    assert any("Unknown tool" in a for a in printed_args)
    assert any("tool list" in a for a in printed_args)
