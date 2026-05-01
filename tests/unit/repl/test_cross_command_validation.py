"""Tests that tool-name validation is consistent across scan, purge, search."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.repl.commands.knowledge_commands import KnowledgeCommands  # noqa: E402
from application.repl.commands.purge import PurgeCommand  # noqa: E402
from application.repl.commands.scan_commands import ScanCommands  # noqa: E402

_VALID_TOOLS = ["semgrep", "gitleaks"]
_INVALID_TOOL = "nonexistent-tool"
_VALID_TOOL = "semgrep"


# ---------------------------------------------------------------------------
# Invalid tool — all three commands reject it
# ---------------------------------------------------------------------------


@patch("application.repl.commands.scan_commands.tool_registry")
def test_invalid_tool_rejected_by_scan(mock_reg):
    mock_reg.list_tool_names.return_value = _VALID_TOOLS
    repl = MagicMock()
    repl.active_project = "proj"
    ScanCommands(repl).cmd_scan("scan", [f"--tool={_INVALID_TOOL}"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Unknown tool" in p for p in printed)


@patch("application.repl.commands.purge.tool_registry")
def test_invalid_tool_rejected_by_purge(mock_reg):
    mock_reg.list_tool_names.return_value = _VALID_TOOLS
    repl = MagicMock()
    repl.active_project = "proj"
    PurgeCommand(repl).cmd_purge("purge", [f"--tool={_INVALID_TOOL}"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Unknown tool" in p for p in printed)


def test_invalid_tool_rejected_by_search():
    repl = MagicMock()
    repl.active_project = "proj"
    kc = KnowledgeCommands(repl)
    mock_qe = MagicMock()
    mock_qe._known_tools = frozenset(_VALID_TOOLS)
    kc._get_query_engine = MagicMock(return_value=mock_qe)
    kc.cmd_search("search", [f"--tool={_INVALID_TOOL}"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)


# ---------------------------------------------------------------------------
# Valid tool — none print "Unknown tool" / "Search error"
# ---------------------------------------------------------------------------


@patch("application.repl.commands.scan_commands.tool_registry")
@patch("application.repl.commands.scan_commands.get_scan_service")
def test_valid_tool_accepted_by_scan(mock_get_service, mock_reg):
    mock_reg.list_tool_names.return_value = _VALID_TOOLS
    repl = MagicMock()
    repl.active_project = "proj"
    repl.config.load_repositories.return_value = []
    repl.project_registry.resolve_by_name.return_value = {"id": 1}

    mock_handle = MagicMock(run_id=1)
    mock_handle.result.result.return_value = MagicMock(findings_by_tool={})
    mock_get_service.return_value.start_scan.return_value = mock_handle

    ScanCommands(repl).cmd_scan("scan", [f"--tool={_VALID_TOOL}"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Unknown tool" in p for p in printed)


@patch("application.repl.commands.purge.tool_registry")
def test_valid_tool_accepted_by_purge(mock_reg):
    mock_reg.list_tool_names.return_value = _VALID_TOOLS
    repl = MagicMock()
    repl.active_project = "proj"
    pc = PurgeCommand(repl)
    mock_kb = MagicMock()
    mock_kb.count.return_value = 0  # exits early after no-match check
    pc._get_knowledge_base = MagicMock(return_value=mock_kb)
    pc.cmd_purge("purge", [f"--tool={_VALID_TOOL}"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Unknown tool" in p for p in printed)


def test_valid_tool_accepted_by_search():
    repl = MagicMock()
    repl.active_project = "proj"
    kc = KnowledgeCommands(repl)
    mock_qe = MagicMock()
    mock_qe._known_tools = frozenset(_VALID_TOOLS)
    mock_qe.search.return_value = []
    kc._get_query_engine = MagicMock(return_value=mock_qe)
    kc.cmd_search("search", [f"--tool={_VALID_TOOL}"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)
