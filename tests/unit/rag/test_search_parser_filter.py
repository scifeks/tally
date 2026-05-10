"""parse_search_query and parse_chromadb_search_command emit Filter AST."""

from __future__ import annotations

import pytest

from application.ports.filters import And, Contains, Eq
from application.rag.search_parser import (
    SearchQuery,
    _resolve_type_filter,
    parse_search_query,
)
from application.repl.search_command_parser import parse_chromadb_search_command
from core.exceptions import SearchValidationError

_KNOWN_TOOLS = frozenset({"gitleaks", "semgrep", "zap", "pip-audit"})
_CMD_KNOWN_TOOLS = frozenset({"semgrep", "gitleaks", "zap"})


def _parse(raw: str) -> SearchQuery:
    return parse_search_query(raw, _KNOWN_TOOLS)


def _cmd_parse(args: list[str]) -> SearchQuery:
    return parse_chromadb_search_command(args, _CMD_KNOWN_TOOLS)


class TestParseSearchQueryFilterAst:
    def test_bare_tool_emits_eq(self) -> None:
        assert _parse("gitleaks").where_filter == Eq("tool", "gitleaks")

    def test_explicit_tool_emits_eq(self) -> None:
        assert _parse("tool=gitleaks").where_filter == Eq("tool", "gitleaks")

    def test_type_secret_emits_eq_true(self) -> None:
        assert _parse("type=secret").where_filter == Eq("type_secret", True)

    def test_type_multiple_emits_and(self) -> None:
        assert _parse("type=vulnerability,misconfiguration").where_filter == And(
            clauses=(
                Eq("type_vulnerability", True),
                Eq("type_misconfiguration", True),
            )
        )

    def test_severity_emits_eq(self) -> None:
        assert _parse("severity=high").where_filter == Eq("severity", "high")

    def test_file_eq_uses_contains_for_always_contains_field(self) -> None:
        assert _parse("file=auth").where_filter == Contains("file_path", "auth")

    def test_file_tilde_emits_contains(self) -> None:
        assert _parse("file~=auth").where_filter == Contains("file_path", "auth")

    def test_host_emits_eq_string(self) -> None:
        assert _parse("host=1.2.3.4").where_filter == Eq("ip_address", "1.2.3.4")

    def test_port_emits_eq_int(self) -> None:
        clause = _parse("port=443").where_filter
        assert clause == Eq("port", 443)
        assert isinstance(clause, Eq)
        assert isinstance(clause.value, int)

    def test_method_uppercased(self) -> None:
        assert _parse("method=get").where_filter == Eq("method", "GET")

    def test_compound_emits_and(self) -> None:
        assert _parse(
            "tool=semgrep type=vulnerability severity=high"
        ).where_filter == And(
            clauses=(
                Eq("tool", "semgrep"),
                Eq("type_vulnerability", True),
                Eq("severity", "high"),
            )
        )

    def test_pure_semantic_has_no_filter(self) -> None:
        sq = _parse("cross site scripting")
        assert sq.semantic_text == "cross site scripting"
        assert sq.where_filter is None

    def test_semantic_with_tool_keeps_eq(self) -> None:
        sq = _parse("tool=semgrep cross site scripting")
        assert sq.semantic_text == "cross site scripting"
        assert sq.where_filter == Eq("tool", "semgrep")


class TestResolveTypeFilter:
    def test_single(self) -> None:
        assert _resolve_type_filter("secret") == Eq("type_secret", True)

    def test_multiple(self) -> None:
        assert _resolve_type_filter("vulnerability,weakness") == And(
            clauses=(
                Eq("type_vulnerability", True),
                Eq("type_weakness", True),
            )
        )

    def test_invalid_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="Unknown type"):
            _resolve_type_filter("unknown")


class TestParseChromaDBSearchCommandFilterAst:
    def test_tool_flag_emits_eq(self) -> None:
        assert _cmd_parse(["--tool=gitleaks"]).where_filter == Eq("tool", "gitleaks")

    def test_multi_tool_emits_and(self) -> None:
        assert _cmd_parse(["--tool=gitleaks,semgrep"]).where_filter == And(
            clauses=(Eq("tool", "gitleaks"), Eq("tool", "semgrep"))
        )

    def test_severity_flag_emits_eq(self) -> None:
        assert _cmd_parse(["--severity=high"]).where_filter == Eq("severity", "high")

    def test_multi_severity_emits_and(self) -> None:
        assert _cmd_parse(["--severity=high,critical"]).where_filter == And(
            clauses=(Eq("severity", "high"), Eq("severity", "critical"))
        )

    def test_type_flag_emits_eq_true(self) -> None:
        assert _cmd_parse(["--type=secret"]).where_filter == Eq("type_secret", True)

    def test_arbitrary_exact_emits_eq(self) -> None:
        assert _cmd_parse(["--description=foo"]).where_filter == Eq(
            "description", "foo"
        )

    def test_arbitrary_partial_emits_contains(self) -> None:
        assert _cmd_parse(["--url~=/api/"]).where_filter == Contains("url", "/api/")

    def test_file_partial_uses_file_path_field(self) -> None:
        assert _cmd_parse(["--file~=src/main"]).where_filter == Contains(
            "file_path", "src/main"
        )

    def test_no_args_yields_no_filter(self) -> None:
        sq = _cmd_parse([])
        assert sq.where_filter is None
        assert sq.is_semantic is False
