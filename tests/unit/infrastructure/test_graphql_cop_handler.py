"""Unit tests for GraphqlCopHandler."""

from __future__ import annotations

from unittest.mock import MagicMock

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.graphql_cop import (
    GraphqlCopHandler,
    _parse_data,
)

_INTROSPECTION = {
    "title": "Introspection Query Enabled",
    "severity": "HIGH",
    "description": "Introspection is enabled.",
    "impact": "Information Leakage",
    "result": True,
    "curl_verify": "curl -X POST ...",
}

_FIELD_SUGGESTIONS = {
    "title": "Field Suggestions Enabled",
    "severity": "LOW",
    "description": "Field suggestions are returned.",
    "impact": "Information Leakage",
    "result": True,
    "curl_verify": "curl ...",
}


def _make_result(findings: list[dict], url: str = "") -> ToolResult:
    mock = MagicMock(spec=ToolResult)
    mock.parsed_data = {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
        "target_url": url,
    }
    mock.timestamp = "2024-01-01T00:00:00"
    mock.output_files = {}
    return mock


class TestGraphqlCopHandlerNormalize:
    def test_empty_findings_returns_empty(self) -> None:
        handler = GraphqlCopHandler()
        result = _make_result([], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows == []

    def test_tool_name_is_graphql_cop(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["tool"] == "graphql-cop"

    def test_domain_is_web(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["domain"] == "web"

    def test_segment_is_web(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["segment"] == "web"

    def test_severity_mapped_from_finding(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["severity"] == "high"

    def test_rule_id_is_slugified_title(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["rule_id"] == "introspection-query-enabled"

    def test_url_from_parsed_data(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["url"] == "https://t.com/graphql"

    def test_type_vulnerability_flag_true(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["type_vulnerability"] is True

    def test_other_type_flags_false(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        for flag in (
            "type_secret",
            "type_dependency",
            "type_misconfiguration",
        ):
            assert rows[0][flag] is False

    def test_meta_contains_impact(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["meta"]["impact"] == "Information Leakage"

    def test_meta_contains_curl_verify(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert "curl" in rows[0]["meta"]["curl_verify"]

    def test_meta_contains_title_raw(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert rows[0]["meta"]["title_raw"] == "Introspection Query Enabled"

    def test_multiple_findings(self) -> None:
        handler = GraphqlCopHandler()
        parsed = _parse_data([_INTROSPECTION, _FIELD_SUGGESTIONS])
        result = _make_result(parsed["findings"], url="https://t.com/graphql")
        rows = handler.normalize(result, "default")
        assert len(rows) == 2


class TestGraphqlCopHandlerRender:
    def test_render_contains_severity_and_title(self) -> None:
        handler = GraphqlCopHandler()
        row = {
            "severity": "high",
            "title": "Introspection Query Enabled",
            "url": "https://t.com/graphql",
        }
        rendered = handler.render(row)
        assert "high" in rendered
        assert "Introspection Query Enabled" in rendered
        assert "https://t.com/graphql" in rendered

    def test_render_format(self) -> None:
        handler = GraphqlCopHandler()
        row = {
            "severity": "low",
            "title": "Field Suggestions Enabled",
            "url": "https://t.com/graphql",
        }
        rendered = handler.render(row)
        assert rendered == ("[low] Field Suggestions Enabled - https://t.com/graphql")


class TestGraphqlCopHandlerFingerprint:
    def test_starts_with_tool_name(self) -> None:
        handler = GraphqlCopHandler()
        key = handler.fingerprint_key(
            {
                "rule_id": "introspection-query-enabled",
                "url": "https://t.com/graphql",
            }
        )
        assert key.startswith("graphql-cop|")

    def test_includes_slug_and_url(self) -> None:
        handler = GraphqlCopHandler()
        key = handler.fingerprint_key(
            {
                "rule_id": "introspection-query-enabled",
                "url": "https://t.com/graphql",
            }
        )
        assert "introspection-query-enabled" in key
        assert "https://t.com/graphql" in key

    def test_empty_finding_stable(self) -> None:
        handler = GraphqlCopHandler()
        key = handler.fingerprint_key({})
        assert key == "graphql-cop||"

    def test_different_url_different_key(self) -> None:
        handler = GraphqlCopHandler()
        k1 = handler.fingerprint_key(
            {
                "rule_id": "introspection-query-enabled",
                "url": "https://a.com/graphql",
            }
        )
        k2 = handler.fingerprint_key(
            {
                "rule_id": "introspection-query-enabled",
                "url": "https://b.com/graphql",
            }
        )
        assert k1 != k2
