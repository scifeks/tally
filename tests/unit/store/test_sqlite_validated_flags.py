"""Unit tests for SQLite search command validated flags."""

from __future__ import annotations

import pytest

from application.repl.search_command_parser import parse_sqlite_search_command
from core.exceptions import SearchValidationError


class TestValidatedFlags:
    _known: frozenset[str] = frozenset({"gitleaks", "semgrep", "nmap"})

    def test_invalid_tool_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="not found"):
            parse_sqlite_search_command(["--tool=badtool"], self._known)

    def test_valid_tool_passes(self) -> None:
        result = parse_sqlite_search_command(["--tool=gitleaks"], self._known)
        conds = result["conditions"]
        assert len(conds) == 1
        col, op, vals = conds[0]
        assert col == "tool"
        assert op == "="
        assert vals == ["gitleaks"]

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="severity"):
            parse_sqlite_search_command(["--severity=extreme"], self._known)

    def test_valid_severity_passes(self) -> None:
        result = parse_sqlite_search_command(["--severity=high"], self._known)
        col, op, vals = result["conditions"][0]
        assert col == "severity" and op == "=" and vals == ["high"]

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="type"):
            parse_sqlite_search_command(["--type=bogus"], self._known)

    def test_invalid_domain_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="domain"):
            parse_sqlite_search_command(["--domain=space"], self._known)

    def test_contains_bypasses_validation(self) -> None:
        result = parse_sqlite_search_command(["--severity~=crit"], self._known)
        assert result["conditions"][0][1] == "~="

    def test_tool_contains_bypasses_validation(self) -> None:
        result = parse_sqlite_search_command(["--tool~=leak"], self._known)
        col, op, vals = result["conditions"][0]
        assert op == "~=" and vals == ["leak"]

    def test_meta_flag_resolves_to_json_extract(self) -> None:
        result = parse_sqlite_search_command(["--risk_type=sql_injection"], self._known)
        col, op, vals = result["conditions"][0]
        assert "json_extract" in col
        assert "risk_type" in col

    def test_alert_maps_to_alert_name(self) -> None:
        result = parse_sqlite_search_command(["--alert=sqli"], self._known)
        col, _, _ = result["conditions"][0]
        assert "alert_name" in col

    def test_unknown_flag_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="Unknown filter flag"):
            parse_sqlite_search_command(["--nonexistent=foo"], self._known)

    def test_csv_tool_produces_in_list(self) -> None:
        result = parse_sqlite_search_command(["--tool=gitleaks,semgrep"], self._known)
        col, op, vals = result["conditions"][0]
        assert op == "=" and vals == ["gitleaks", "semgrep"]

    def test_pagination_flags(self) -> None:
        result = parse_sqlite_search_command(
            ["--page=3", "--page-size=10"], self._known
        )
        assert result["page"] == 3
        assert result["page_size"] == 10

    def test_bad_page_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="--page"):
            parse_sqlite_search_command(["--page=0"], self._known)

    def test_bad_page_size_raises(self) -> None:
        with pytest.raises(SearchValidationError, match="--page-size"):
            parse_sqlite_search_command(["--page-size=-1"], self._known)
