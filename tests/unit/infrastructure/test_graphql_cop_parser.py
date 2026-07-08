"""Unit tests for the graphql-cop parser."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.parsers.graphql_cop import (
    parse_graphql_cop_json,
    parse_graphql_cop_json_string,
)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "ingest"
    / "graphql_cop_scan.json"
)

_TRUE_FINDING = {
    "title": "Introspection Query Enabled",
    "severity": "HIGH",
    "description": "Introspection is enabled.",
    "impact": "Information Leakage",
    "result": True,
    "curl_verify": "curl -X POST ...",
}

_FALSE_FINDING = {
    "title": "Batch Query Support",
    "severity": "INFO",
    "description": "Server supports batch queries.",
    "impact": "Denial of Service",
    "result": False,
}


class TestParseGraphqlCopJsonStringEdgeCases:
    def test_empty_string_returns_empty(self) -> None:
        result = parse_graphql_cop_json_string("")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_whitespace_returns_empty(self) -> None:
        result = parse_graphql_cop_json_string("   \n\t  ")
        assert result["findings"] == []

    def test_invalid_json_returns_empty(self) -> None:
        result = parse_graphql_cop_json_string("not json")
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_json_object_not_array_returns_empty(self) -> None:
        result = parse_graphql_cop_json_string('{"key": "value"}')
        assert result["findings"] == []

    def test_empty_array_returns_empty(self) -> None:
        result = parse_graphql_cop_json_string("[]")
        assert result["findings"] == []


class TestParseGraphqlCopJsonStringFiltering:
    def test_result_true_included(self) -> None:
        data = json.dumps([_TRUE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert len(result["findings"]) == 1

    def test_result_false_excluded(self) -> None:
        data = json.dumps([_FALSE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert result["findings"] == []

    def test_mixed_results_filters_correctly(self) -> None:
        data = json.dumps([_TRUE_FINDING, _FALSE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert len(result["findings"]) == 1
        assert result["summary"]["total_findings"] == 1


class TestParseGraphqlCopJsonStringSeverityMapping:
    def test_high_maps_to_high(self) -> None:
        finding = dict(_TRUE_FINDING, severity="HIGH")
        result = parse_graphql_cop_json_string(json.dumps([finding]))
        assert result["findings"][0]["severity"] == "high"

    def test_medium_maps_to_medium(self) -> None:
        finding = dict(_TRUE_FINDING, severity="MEDIUM")
        result = parse_graphql_cop_json_string(json.dumps([finding]))
        assert result["findings"][0]["severity"] == "medium"

    def test_low_maps_to_low(self) -> None:
        finding = dict(_TRUE_FINDING, severity="LOW")
        result = parse_graphql_cop_json_string(json.dumps([finding]))
        assert result["findings"][0]["severity"] == "low"

    def test_info_maps_to_informational(self) -> None:
        finding = dict(_TRUE_FINDING, severity="INFO")
        result = parse_graphql_cop_json_string(json.dumps([finding]))
        assert result["findings"][0]["severity"] == "informational"


class TestParseGraphqlCopJsonStringFieldExtraction:
    def test_title_extracted(self) -> None:
        data = json.dumps([_TRUE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert result["findings"][0]["title"] == "Introspection Query Enabled"

    def test_description_extracted(self) -> None:
        data = json.dumps([_TRUE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert result["findings"][0]["description"] != ""

    def test_impact_extracted(self) -> None:
        data = json.dumps([_TRUE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert result["findings"][0]["impact"] == "Information Leakage"

    def test_curl_verify_extracted(self) -> None:
        data = json.dumps([_TRUE_FINDING])
        result = parse_graphql_cop_json_string(data)
        assert result["findings"][0]["curl_verify"] != ""

    def test_missing_optional_fields_default_empty(self) -> None:
        minimal = {"title": "Test", "severity": "LOW", "result": True}
        result = parse_graphql_cop_json_string(json.dumps([minimal]))
        f = result["findings"][0]
        assert f["description"] == ""
        assert f["impact"] == ""
        assert f["curl_verify"] == ""


class TestParseGraphqlCopJson:
    def test_reads_fixture_file(self) -> None:
        result = parse_graphql_cop_json(_FIXTURE_PATH)
        assert len(result["findings"]) == 3

    def test_fixture_has_correct_summary(self) -> None:
        result = parse_graphql_cop_json(_FIXTURE_PATH)
        assert result["summary"]["total_findings"] == 3

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        result = parse_graphql_cop_json(tmp_path / "nonexistent.json")
        assert "error" in result
        assert result["findings"] == []
