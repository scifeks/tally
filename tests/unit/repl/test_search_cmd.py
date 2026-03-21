"""Tests for cmd_search at the REPL level using mocked query engine."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.repl.commands.knowledge_commands import KnowledgeCommands  # noqa: E402

_KNOWN_TOOLS = frozenset({"nmap", "semgrep", "gitleaks", "zap"})


def _make_repl_and_kc(active_project: str | None = "testproj"):
    repl = MagicMock()
    repl.active_project = active_project
    repl.console = MagicMock()
    kc = KnowledgeCommands(repl)
    return repl, kc


def _make_mock_qe(results=None):
    mock_qe = MagicMock()
    mock_qe._known_tools = _KNOWN_TOOLS
    mock_qe.search.return_value = results if results is not None else []
    return mock_qe


def _make_mock_store(results=None):
    """Create a mock SQLiteStore that returns given results from search()."""
    mock_store = MagicMock()
    mock_store.search.return_value = results if results is not None else []
    return mock_store


def _make_results(n=3, tool="nmap", distance=None):
    return [
        {
            "document": f"doc{i}",
            "metadata": {"tool": tool, "severity": "high"},
            "distance": distance,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# --help flag
# ---------------------------------------------------------------------------


def test_search_help_flag_prints_table():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--help"])

    repl.console.print.assert_called()
    mock_store.search.assert_not_called()


def test_search_help_no_project_still_works():
    repl, kc = _make_repl_and_kc(active_project=None)

    kc.cmd_search("search", ["--help"])

    repl.console.print.assert_called()


# ---------------------------------------------------------------------------
# Basic runs
# ---------------------------------------------------------------------------


def test_search_no_args_runs_ok():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", [])

    mock_store.search.assert_called_once()


def test_search_tool_filter():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--tool=semgrep"])

    mock_store.search.assert_called_once()
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)


def test_search_multi_tool():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--tool=nmap,semgrep"])

    mock_store.search.assert_called_once()
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)


def test_search_severity_filter():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--severity=high"])

    mock_store.search.assert_called_once()


def test_search_multi_severity():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--severity=high,critical"])

    mock_store.search.assert_called_once()


# ---------------------------------------------------------------------------
# --type filter
# ---------------------------------------------------------------------------


def test_search_type_filter_invalid():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--type=code"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)
    mock_store.search.assert_not_called()


# ---------------------------------------------------------------------------
# Validation errors printed to console
# ---------------------------------------------------------------------------


def test_search_invalid_tool_prints_error():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--tool=badtool"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)


def test_search_invalid_severity_prints_error():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--severity=invalid"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)


def test_search_invalid_type_prints_error():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--type=invalid"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)


def test_search_old_bare_word_rejected():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["sql", "injection"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)
    mock_store.search.assert_not_called()


def test_search_old_key_equals_rejected():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["tool=semgrep"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)
    mock_store.search.assert_not_called()


# ---------------------------------------------------------------------------
# Arbitrary flag pass-through
# ---------------------------------------------------------------------------


def test_search_file_partial_match():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--file~=src/main"])

    mock_store.search.assert_called_once()
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)


def test_search_description_unknown_flag_rejected():
    """--description is not a supported SQLite filter flag."""
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--description=sql injection"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)
    mock_store.search.assert_not_called()


def test_search_url_partial():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--url~=/api/"])

    mock_store.search.assert_called_once()


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------


def test_search_no_results_prints_message():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store([])
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--tool=nmap"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("No findings matched" in p for p in printed)


# ---------------------------------------------------------------------------
# Pagination hint
# ---------------------------------------------------------------------------


def test_search_page_hint_shown():
    repl, kc = _make_repl_and_kc()
    # Return page_size (200) results to trigger the "next page" hint
    results = _make_results(n=200, tool="nmap")
    mock_store = _make_mock_store(results)
    kc._get_finding_repo = MagicMock(return_value=mock_store)

    kc.cmd_search("search", ["--tool=nmap"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("--page=2" in p for p in printed)


# ---------------------------------------------------------------------------
# No active project
# ---------------------------------------------------------------------------


def test_search_no_active_project_prints_warning():
    repl, kc = _make_repl_and_kc(active_project=None)

    kc.cmd_search("search", ["--tool=nmap"])

    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("No active project" in p for p in printed)


# ---------------------------------------------------------------------------
# --show-fields
# ---------------------------------------------------------------------------


def test_show_fields_without_tool_prints_error():
    repl, kc = _make_repl_and_kc()
    kc.cmd_search("search", ["--show-fields"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Error" in p for p in printed)


def test_show_fields_with_extra_flag_prints_error():
    repl, kc = _make_repl_and_kc()
    kc.cmd_search("search", ["--show-fields", "--tool=gitleaks", "--severity=high"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Error" in p for p in printed)


def test_show_fields_with_value_prints_error():
    """--show-fields=true is invalid; flag takes no value."""
    repl, kc = _make_repl_and_kc()
    kc.cmd_search("search", ["--show-fields=true", "--tool=gitleaks"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Error" in p for p in printed)


def test_show_fields_multi_tool_prints_error():
    """--tool=a,b is not allowed with --show-fields (single tool only)."""
    repl, kc = _make_repl_and_kc()
    kc.cmd_search("search", ["--show-fields", "--tool=gitleaks,semgrep"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Error" in p for p in printed)


def test_show_fields_no_rows_prints_message():
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    mock_store.get_tool_meta_keys.return_value = (0, set())
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--show-fields", "--tool=gitleaks"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("No findings" in p for p in printed)


def test_show_fields_returns_sorted_fields():
    """With known meta keys + gitleaks normalized config, output is sorted & merged."""
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    mock_store.get_tool_meta_keys.return_value = (5, {"risk_type", "line_number"})
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--show-fields", "--tool=gitleaks"])
    printed = [str(c) for c in repl.console.print.call_args_list]
    # Must include gitleaks normalized fields AND meta keys, sorted
    output = " ".join(printed)
    assert "confidence" in output
    assert "file_path" in output
    assert "line_number" in output
    assert "risk_type" in output


# ---------------------------------------------------------------------------
# --fields
# ---------------------------------------------------------------------------


def test_fields_valid_calls_store():
    """--fields with valid names calls store and prints no error."""
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store(_make_results(n=2))
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--fields=severity,tool"])
    mock_store.search.assert_called_once()
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)


def test_fields_empty_value_prints_error():
    """--fields= (empty) prints a Search error and does not call store."""
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store()
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--fields="])
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert any("Search error" in p for p in printed)
    mock_store.search.assert_not_called()


def test_fields_without_tool_filter_works():
    """--fields works without --tool (absent keys render as N/A)."""
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store(_make_results(n=1))
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--fields=severity,file_path"])
    mock_store.search.assert_called_once()
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)


def test_fields_combined_with_filter():
    """--fields combined with --severity filter passes both to store."""
    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store(_make_results(n=1))
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--severity=high", "--fields=severity,tool"])
    mock_store.search.assert_called_once()
    printed = [str(c) for c in repl.console.print.call_args_list]
    assert not any("Search error" in p for p in printed)


def test_fields_column_order_preserved():
    """Column headers in the rendered table match --fields order exactly."""
    from rich.table import Table as RichTable

    repl, kc = _make_repl_and_kc()
    mock_store = _make_mock_store(_make_results(n=1, tool="nmap"))
    kc._get_finding_repo = MagicMock(return_value=mock_store)
    kc.cmd_search("search", ["--fields=severity,tool,confidence"])
    tables = [
        c.args[0]
        for c in repl.console.print.call_args_list
        if c.args and isinstance(c.args[0], RichTable)
    ]
    assert len(tables) == 1
    assert [col.header for col in tables[0].columns] == [
        "severity",
        "tool",
        "confidence",
    ]
