"""Tests for scan start and resume background mode flags."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from application.repl.exceptions import ReplArgumentError


@pytest.fixture
def repl():
    """Mock REPL instance."""
    repl_mock = MagicMock()
    out_stream = StringIO()
    repl_mock.console = Console(file=out_stream, width=120, force_terminal=False)
    repl_mock.base_path = "/tmp/tally"
    repl_mock.active_project = "test-project"
    repl_mock.project_registry = MagicMock()
    repl_mock.project_registry.resolve_by_name.return_value = MagicMock(id=1)
    repl_mock._get_output = lambda: out_stream.getvalue()
    return repl_mock


def test_scan_start_background_plan(repl):
    """Scan start with background mode and plan billing parses flags correctly."""
    from application.repl.commands.scan_commands import ScanCommands

    cmd = ScanCommands(repl)
    mode, billing, api_key, only, exclude = cmd._parse_mode_flags(
        ["--background", "--billing", "plan", "--only", "scan-xss-stored"]
    )

    assert mode == "background"
    assert billing == "plan"
    assert only == ["scan-xss-stored"]
    assert exclude is None
    assert api_key is None


def test_scan_start_rejects_both_flags(repl):
    """Scan start rejects --only and --exclude simultaneously."""
    from application.repl.commands.scan_commands import ScanCommands

    cmd = ScanCommands(repl)
    with pytest.raises(ReplArgumentError, match="mutually exclusive"):
        cmd._parse_mode_flags(
            [
                "--background",
                "--billing",
                "plan",
                "--only",
                "scan-xss-stored",
                "--exclude",
                "scan-injection-sql",
            ]
        )


def test_only_rejects_flag_as_value(repl):
    """--only followed by another flag raises instead of silently consuming it."""
    from application.repl.commands.scan_commands import ScanCommands

    cmd = ScanCommands(repl)
    with pytest.raises(ReplArgumentError, match="requires a comma-separated value"):
        cmd._parse_mode_flags(["--only", "--exclude", "scan-injection-sql"])


def test_exclude_rejects_flag_as_value(repl):
    """--exclude followed by another flag raises instead of silently consuming it."""
    from application.repl.commands.scan_commands import ScanCommands

    cmd = ScanCommands(repl)
    with pytest.raises(ReplArgumentError, match="requires a comma-separated value"):
        cmd._parse_mode_flags(["--exclude", "--background"])


def test_billing_missing_value_raises():
    """--billing without a value raises ReplArgumentError."""
    from application.repl.commands.scan_commands import _parse_shared_mode_flags

    with pytest.raises(ReplArgumentError, match="--billing requires a value"):
        _parse_shared_mode_flags(["--billing"])


def test_api_key_override_missing_value_raises():
    """--api-key-override without a value raises ReplArgumentError."""
    from application.repl.commands.scan_commands import _parse_shared_mode_flags

    with pytest.raises(ReplArgumentError, match="--api-key-override requires a value"):
        _parse_shared_mode_flags(["--api-key-override"])
