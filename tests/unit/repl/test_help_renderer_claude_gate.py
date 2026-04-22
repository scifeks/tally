"""Tests for HelpRenderer triage-greying when Claude Code is missing."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from application.repl.help_renderer import HelpRenderer


def _runtime_service(installed: bool) -> MagicMock:
    svc = MagicMock()
    svc.is_installed.return_value = installed
    return svc


def _render_table(installed: bool) -> str:
    buf = StringIO()
    console = Console(file=buf, highlight=False, markup=True)
    renderer = HelpRenderer(console, runtime_service=_runtime_service(installed))
    renderer.render_all()
    return buf.getvalue()


class TestHelpRendererClaudePresent:
    def test_triage_rows_not_dimmed(self) -> None:
        output = _render_table(installed=True)
        assert "(Claude Code required)" not in output

    def test_triage_command_visible(self) -> None:
        output = _render_table(installed=True)
        assert "triage" in output


class TestHelpRendererClaudeMissing:
    def test_triage_rows_have_required_prefix(self) -> None:
        output = _render_table(installed=False)
        assert "Claude Code required" in output

    def test_non_triage_rows_unaffected(self) -> None:
        output = _render_table(installed=False)
        assert "project add" in output
        assert "scan" in output

    def test_no_runtime_service_no_greying(self) -> None:
        buf = StringIO()
        console = Console(file=buf, highlight=False, markup=True)
        renderer = HelpRenderer(console, runtime_service=None)
        renderer.render_all()
        output = buf.getvalue()
        assert "(Claude Code required)" not in output
