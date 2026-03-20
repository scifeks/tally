"""Tests for core.rag.search_parser and knowledge_commands display helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.exceptions import SearchValidationError  # noqa: E402
from core.rag.search_parser import (  # noqa: E402
    SearchQuery,
    _resolve_type_filter,
    parse_search_query,
)
from core.repl.commands.findings_table import (  # noqa: E402
    _extract_types,
    color_severity,
)
from core.repl.search_command_parser import parse_chromadb_search_command  # noqa: E402

_KNOWN_TOOLS = frozenset({"nmap", "gitleaks", "semgrep", "zap", "pip-audit"})


def _parse(raw: str) -> SearchQuery:
    return parse_search_query(raw, _KNOWN_TOOLS)


# ---------------------------------------------------------------------------
# Query builder tests — pure unit, no ChromaDB
# ---------------------------------------------------------------------------


def test_bare_tool_name_becomes_tool_filter():
    sq = _parse("gitleaks")
    assert sq.where_filter == {"tool": {"$eq": "gitleaks"}}
    assert sq.is_semantic is False
    assert sq.semantic_text is None


def test_explicit_tool_filter():
    sq = _parse("tool=gitleaks")
    assert sq.where_filter == {"tool": {"$eq": "gitleaks"}}
    assert sq.is_semantic is False


def test_type_secret():
    sq = _parse("type=secret")
    assert sq.where_filter == {"type_secret": {"$eq": True}}


def test_type_multiple():
    sq = _parse("type=vulnerability,misconfiguration")
    assert sq.where_filter == {
        "$and": [
            {"type_vulnerability": {"$eq": True}},
            {"type_misconfiguration": {"$eq": True}},
        ]
    }


def test_severity_filter():
    sq = _parse("severity=high")
    assert sq.where_filter == {"severity": {"$eq": "high"}}


def test_file_always_contains():
    sq = _parse("file=auth")
    assert sq.where_filter == {"file_path": {"$contains": "auth"}}


def test_file_tilde_contains():
    sq = _parse("file~=auth")
    assert sq.where_filter == {"file_path": {"$contains": "auth"}}


def test_host_exact():
    sq = _parse("host=1.2.3.4")
    assert sq.where_filter == {"ip_address": {"$eq": "1.2.3.4"}}


def test_port_int():
    sq = _parse("port=443")
    assert sq.where_filter == {"port": {"$eq": 443}}
    assert sq.where_filter is not None
    assert isinstance(sq.where_filter["port"]["$eq"], int)


def test_method_uppercased():
    sq = _parse("method=get")
    assert sq.where_filter == {"method": {"$eq": "GET"}}


def test_compound_and():
    sq = _parse("tool=semgrep type=vulnerability severity=high")
    assert sq.where_filter == {
        "$and": [
            {"tool": {"$eq": "semgrep"}},
            {"type_vulnerability": {"$eq": True}},
            {"severity": {"$eq": "high"}},
        ]
    }


def test_pure_semantic():
    sq = _parse("cross site scripting")
    assert sq.semantic_text == "cross site scripting"
    assert sq.where_filter is None


def test_semantic_with_tool():
    sq = _parse("tool=semgrep cross site scripting")
    assert sq.semantic_text == "cross site scripting"
    assert sq.where_filter == {"tool": {"$eq": "semgrep"}}


def test_bare_tool_plus_semantic():
    sq = _parse("gitleaks aws access key")
    assert sq.semantic_text == "aws access key"
    assert sq.where_filter == {"tool": {"$eq": "gitleaks"}}


def test_semantic_is_true():
    sq = _parse("cross site scripting")
    assert sq.is_semantic is True


def test_metadata_only_is_false():
    sq = _parse("type=secret")
    assert sq.is_semantic is False


# ---------------------------------------------------------------------------
# Pagination tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Validation error tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Type resolver tests — direct calls to _resolve_type_filter
# ---------------------------------------------------------------------------


def test_single_type_resolves():
    result = _resolve_type_filter("secret")
    assert result == {"type_secret": {"$eq": True}}


def test_multiple_types_resolve():
    result = _resolve_type_filter("vulnerability,weakness")
    assert result == {
        "$and": [
            {"type_vulnerability": {"$eq": True}},
            {"type_weakness": {"$eq": True}},
        ]
    }


def test_invalid_type_raises_direct():
    with pytest.raises(SearchValidationError, match="Unknown type"):
        _resolve_type_filter("unknown")


# ---------------------------------------------------------------------------
# Results display tests — pure unit, helpers only
# ---------------------------------------------------------------------------


def test_extract_types_single():
    assert _extract_types({"type_vulnerability": True}) == "vulnerability"


def test_extract_types_multiple():
    meta = {"type_vulnerability": True, "type_weakness": True}
    result = _extract_types(meta)
    # sorted: ...vulnerability, weakness
    assert result == "vulnerability, weakness"


def test_extract_types_none_true():
    assert _extract_types({"type_vulnerability": False}) == ""


def test_extract_types_empty_meta():
    assert _extract_types({}) == ""


def testcolor_severity_critical():
    result = color_severity("critical")
    assert "red" in result


def testcolor_severity_low():
    result = color_severity("low")
    assert "blue" in result


def testcolor_severity_unknown():
    result = color_severity("unknown_value")
    assert "white" in result


def testcolor_severity_empty():
    assert color_severity("") == ""


# ---------------------------------------------------------------------------
# Confidence filter tests
# ---------------------------------------------------------------------------


def test_confidence_filter():
    sq = _parse("confidence=confirmed")
    assert sq.where_filter == {"confidence": {"$eq": "confirmed"}}


def test_invalid_confidence_raises():
    with pytest.raises(SearchValidationError, match="Valid confidence levels"):
        _parse("confidence=high")


def test_severity_confirmed_raises_with_new_schema():
    with pytest.raises(SearchValidationError, match="Unknown severity"):
        _parse("severity=confirmed")


# ---------------------------------------------------------------------------
# No results test
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Contextual error message tests
# ---------------------------------------------------------------------------


def test_unknown_key_error_without_tool_suggests_help_search():
    with pytest.raises(SearchValidationError, match="help search"):
        _parse("finding=foo")


def test_unknown_key_error_with_nmap_suggests_help_search_nmap():
    with pytest.raises(SearchValidationError, match="help search nmap"):
        _parse("tool=nmap finding=foo")


def test_unknown_key_error_with_gitleaks_suggests_help_search_gitleaks():
    with pytest.raises(SearchValidationError, match="help search gitleaks"):
        _parse("tool=gitleaks finding=foo")


def test_unknown_key_error_with_tool_after_bad_key_uses_tool_context():
    # Pre-scan finds tool=nmap even though the bad key comes first.
    with pytest.raises(SearchValidationError, match="help search nmap"):
        _parse("finding=foo tool=nmap")


# ---------------------------------------------------------------------------


def test_no_results_message():
    """When search returns [], cmd_search prints the 'No findings' message."""
    from core.repl.commands.knowledge_commands import KnowledgeCommands

    repl = MagicMock()
    repl.active_project = "test_project"

    kc = KnowledgeCommands(repl)

    mock_qe = MagicMock()
    mock_qe.search.return_value = []
    mock_qe._known_tools = frozenset({"nmap", "gitleaks"})
    kc._get_query_engine = MagicMock(return_value=mock_qe)

    kc.cmd_search("search", ["--type=secret"])

    printed_args = [str(call) for call in repl.console.print.call_args_list]
    assert any("No findings matched" in a for a in printed_args)


# ---------------------------------------------------------------------------
# parse_search_command tests
# ---------------------------------------------------------------------------

_CMD_KNOWN_TOOLS = frozenset({"nmap", "semgrep", "gitleaks", "zap"})


def _cmd_parse(args: list[str]) -> SearchQuery:
    return parse_chromadb_search_command(args, _CMD_KNOWN_TOOLS)


def test_search_cmd_bare_word_rejected():
    with pytest.raises(SearchValidationError, match="Unexpected argument"):
        _cmd_parse(["sql"])


def test_search_cmd_old_key_equals_rejected():
    with pytest.raises(SearchValidationError, match="Old syntax"):
        _cmd_parse(["tool=nmap"])


def test_search_cmd_tool_flag():
    sq = _cmd_parse(["--tool=nmap"])
    assert sq.where_filter == {"tool": {"$eq": "nmap"}}


def test_search_cmd_multi_tool():
    sq = _cmd_parse(["--tool=nmap,semgrep"])
    assert sq.where_filter == {
        "$and": [{"tool": {"$eq": "nmap"}}, {"tool": {"$eq": "semgrep"}}]
    }


def test_search_cmd_severity_flag():
    sq = _cmd_parse(["--severity=high"])
    assert sq.where_filter == {"severity": {"$eq": "high"}}


def test_search_cmd_multi_severity():
    sq = _cmd_parse(["--severity=high,critical"])
    assert sq.where_filter == {
        "$and": [
            {"severity": {"$eq": "high"}},
            {"severity": {"$eq": "critical"}},
        ]
    }


def test_search_cmd_type_flag():
    sq = _cmd_parse(["--type=secret"])
    assert sq.where_filter == {"type_secret": {"$eq": True}}


def test_search_cmd_arbitrary_exact():
    sq = _cmd_parse(["--description=foo"])
    assert sq.where_filter == {"description": {"$eq": "foo"}}


def test_search_cmd_arbitrary_partial():
    sq = _cmd_parse(["--url~=/api/"])
    assert sq.where_filter == {"url": {"$contains": "/api/"}}


def test_search_cmd_file_partial():
    # --file uses _KEY_MAP → maps to file_path with always_contains=True
    sq = _cmd_parse(["--file~=src/main"])
    assert sq.where_filter == {"file_path": {"$contains": "src/main"}}


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


def test_search_cmd_no_args():
    sq = _cmd_parse([])
    assert sq.where_filter is None
    assert sq.is_semantic is False


def test_search_cmd_is_never_semantic():
    sq = _cmd_parse(["--tool=nmap"])
    assert sq.is_semantic is False
