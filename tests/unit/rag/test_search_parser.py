"""Tests for search_parser pagination, validation, and display helpers.

Filter-AST output assertions live in test_search_parser_filter.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.search_parser import (  # noqa: E402
    SearchQuery,
    parse_search_query,
)
from application.repl.commands.findings_table import (  # noqa: E402
    _extract_types,
    color_severity,
)
from application.repl.search_command_parser import (  # noqa: E402
    parse_chromadb_search_command,
)
from core.exceptions import SearchValidationError  # noqa: E402

_KNOWN_TOOLS = frozenset({"gitleaks", "semgrep", "zap", "pip-audit"})


def _parse(raw: str) -> SearchQuery:
    return parse_search_query(raw, _KNOWN_TOOLS)


# Semantic-vs-metadata classification


def test_semantic_is_true():
    sq = _parse("cross site scripting")
    assert sq.is_semantic is True


def test_metadata_only_is_false():
    sq = _parse("type=secret")
    assert sq.is_semantic is False


def test_bare_tool_plus_semantic_separates():
    sq = _parse("gitleaks aws access key")
    assert sq.semantic_text == "aws access key"


# Pagination tests


def test_default_page():
    sq = _parse("type=secret")
    assert sq.page == 1
    assert sq.page_size == 200


def test_default_semantic_page_size():
    sq = _parse("cross site scripting")
    assert sq.page == 1
    assert sq.page_size == 20


def test_page_size_flag():
    sq = _parse("type=secret --page-size=50")
    assert sq.page_size == 50


def test_page_flag():
    sq = _parse("type=secret --page=3")
    assert sq.page == 3


def test_both_flags():
    sq = _parse("type=secret --page-size=10 --page=2")
    assert sq.page_size == 10
    assert sq.page == 2


def test_page_size_zero_raises():
    with pytest.raises(SearchValidationError):
        _parse("--page-size=0")


def test_page_zero_raises():
    with pytest.raises(SearchValidationError):
        _parse("--page=0")


def test_page_non_int_raises():
    with pytest.raises(SearchValidationError):
        _parse("--page=abc")


def test_unknown_flag_raises():
    with pytest.raises(SearchValidationError, match="Unknown flag"):
        _parse("--limit=5")


def test_flag_without_value_raises():
    with pytest.raises(SearchValidationError):
        _parse("--page-size")


# Validation error tests


def test_unknown_key_raises():
    with pytest.raises(SearchValidationError, match="Unknown filter key"):
        _parse("foo=bar")


def test_invalid_type_raises():
    with pytest.raises(SearchValidationError, match="Unknown type"):
        _parse("type=malware")


def test_invalid_severity_raises():
    with pytest.raises(SearchValidationError, match="Unknown severity"):
        _parse("severity=confirmed")


def test_invalid_domain_raises():
    with pytest.raises(SearchValidationError, match="Unknown domain"):
        _parse("domain=cloud")


def test_unknown_tool_raises():
    with pytest.raises(SearchValidationError, match="not found"):
        _parse("tool=badtool")


def test_port_non_int_raises():
    with pytest.raises(SearchValidationError, match="Port must be a number"):
        _parse("port=https")


def test_invalid_confidence_raises():
    with pytest.raises(SearchValidationError, match="Valid confidence levels"):
        _parse("confidence=high")


def test_severity_confirmed_raises_with_new_schema():
    with pytest.raises(SearchValidationError, match="Unknown severity"):
        _parse("severity=confirmed")


# Contextual error message tests


def test_unknown_key_error_without_tool_suggests_help_search():
    with pytest.raises(SearchValidationError, match="help search"):
        _parse("finding=foo")


def test_unknown_key_error_with_gitleaks_suggests_help_search_gitleaks():
    with pytest.raises(SearchValidationError, match="help search gitleaks"):
        _parse("tool=gitleaks finding=foo")


def test_unknown_key_error_with_tool_after_bad_key_uses_tool_context():
    with pytest.raises(SearchValidationError, match="help search gitleaks"):
        _parse("finding=foo tool=gitleaks")


# Results display tests: pure unit, helpers only


def test_extract_types_single():
    assert _extract_types({"type_vulnerability": True}) == "vulnerability"


def test_extract_types_multiple():
    meta = {"type_vulnerability": True, "type_weakness": True}
    result = _extract_types(meta)
    assert result == "vulnerability, weakness"


def test_extract_types_none_true():
    assert _extract_types({"type_vulnerability": False}) == ""


def test_extract_types_empty_meta():
    assert _extract_types({}) == ""


def testcolor_severity_critical():
    assert "red" in color_severity("critical")


def testcolor_severity_low():
    assert "blue" in color_severity("low")


def testcolor_severity_unknown():
    assert "white" in color_severity("unknown_value")


def testcolor_severity_empty():
    assert color_severity("") == ""


# No-results display test


def test_no_results_message():
    """When search returns [], cmd_search prints the 'No findings' message."""
    from application.repl.commands.knowledge_commands import KnowledgeCommands

    repl = MagicMock()
    repl.active_project = "test_project"
    repl.tool_registry.list_tool_names.return_value = ["semgrep", "gitleaks"]

    kc = KnowledgeCommands(repl)

    mock_repo = MagicMock()
    mock_repo.search.return_value = []
    kc._get_finding_repo = MagicMock(return_value=mock_repo)

    kc.cmd_search("search", ["--type=secret"])

    printed_args = [str(call) for call in repl.console.print.call_args_list]
    assert any("No findings matched" in a for a in printed_args)


# parse_chromadb_search_command: pagination and error tests

_CMD_KNOWN_TOOLS = frozenset({"semgrep", "gitleaks", "zap"})


def _cmd_parse(args: list[str]) -> SearchQuery:
    return parse_chromadb_search_command(args, _CMD_KNOWN_TOOLS)


def test_search_cmd_bare_word_rejected():
    with pytest.raises(SearchValidationError, match="Unexpected argument"):
        _cmd_parse(["sql"])


def test_search_cmd_old_key_equals_rejected():
    with pytest.raises(SearchValidationError, match="Old syntax"):
        _cmd_parse(["tool=gitleaks"])


def test_search_cmd_invalid_tool():
    with pytest.raises(SearchValidationError, match="not found"):
        _cmd_parse(["--tool=badtool"])


def test_search_cmd_invalid_severity():
    with pytest.raises(SearchValidationError, match="Unknown severity"):
        _cmd_parse(["--severity=invalid"])


def test_search_cmd_invalid_type():
    with pytest.raises(SearchValidationError, match="Unknown type"):
        _cmd_parse(["--type=invalid"])


def test_search_cmd_page():
    sq = _cmd_parse(["--page=3"])
    assert sq.page == 3


def test_search_cmd_page_size():
    sq = _cmd_parse(["--page-size=50"])
    assert sq.page_size == 50


def test_search_cmd_is_never_semantic():
    sq = _cmd_parse(["--tool=gitleaks"])
    assert sq.is_semantic is False
