"""Tests for scan skills command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest
from rich.console import Console


@pytest.fixture
def repl():
    """Mock REPL instance with minimal scaffolding."""
    repl_mock = MagicMock()
    out_stream = StringIO()
    repl_mock.console = Console(file=out_stream, width=120, force_terminal=False)
    repl_mock.base_path = "/tmp/tally"
    repl_mock.active_project = "test-project"
    repl_mock._get_output = lambda: out_stream.getvalue()
    return repl_mock


def test_scan_skills_command_outputs_table(repl):
    """Scan skills command prints a formatted table."""
    from application.repl.commands.scan_commands import ScanCommands

    cmd = ScanCommands(repl)
    cmd.cmd_scan_skills("scan skills", [])
    out = repl._get_output()
    assert "scan-xss-stored" in out
    assert "scan-injection-sql" in out
    assert "injection" in out
