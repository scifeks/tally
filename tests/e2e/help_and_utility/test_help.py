"""E2E tests for help and help search commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.e2e


def test_help_displays_full_table(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("help")
    assert "Project Management" in output
    assert "Scanning" in output
    assert "Knowledge Base" in output
    assert "Search" in output
    assert "Utility" in output
    assert "project add" in output
    assert "scan" in output
    assert "search" in output
    assert "help" in output
    assert "exit / quit" in output


def test_help_search_displays_syntax_reference(
    tally_harness: TallyHarness,
) -> None:
    output = tally_harness.run("help search")
    assert "Search Syntax" in output
    assert "--tool=<name>" in output
    assert "Global Filter Keys" in output
    assert "Pagination" in output
    assert "Examples" in output


def test_help_search_tool_shows_tool_scoped_help(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    commands_cfg = tmp_path / "config" / "commands.json"
    commands_cfg.write_text(
        json.dumps(
            {
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/gitleaks",
                }
            }
        )
    )
    output = tally_harness.run("help search gitleaks")
    assert "search --tool=gitleaks" in output
    assert "search --file~=config" in output


def test_help_search_unknown_tool(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("help search nonexistent")
    assert "Unknown tool" in output
