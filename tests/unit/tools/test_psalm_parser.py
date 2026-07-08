"""Tests for Psalm SARIF parser."""

import json
from pathlib import Path

import pytest

from infrastructure.tools.parsers.psalm import (
    parse_psalm_sarif,
    parse_psalm_sarif_string,
)


def _taint_result(
    rule_id: str = "TaintedSql",
    level: str = "error",
    message: str = "Tainted SQL detected",
    uri: str = "app.php",
    line: int = 10,
    col: int | None = None,
    end_line: int | None = None,
    code_flow: bool = True,
) -> dict:
    """Build a SARIF result object with taint findings."""
    result: dict = {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line},
                }
            }
        ],
    }
    if col is not None:
        result["locations"][0]["physicalLocation"]["region"]["startColumn"] = col
    if end_line is not None:
        result["locations"][0]["physicalLocation"]["region"]["endLine"] = end_line

    if code_flow:
        result["codeFlows"] = [
            {
                "threadFlows": [
                    {
                        "locations": [
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": uri},
                                        "region": {"startLine": line},
                                    },
                                    "message": {"text": "$untrusted_input"},
                                }
                            },
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": uri},
                                        "region": {"startLine": line + 1},
                                    },
                                    "message": {"text": "$query"},
                                }
                            },
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": uri},
                                        "region": {"startLine": line + 2},
                                    },
                                    "message": {"text": "$db->execute()"},
                                }
                            },
                        ]
                    }
                ]
            }
        ]
    return result


def _make_sarif(results: list[dict]) -> str:
    """Build a complete SARIF document."""
    return json.dumps({"runs": [{"results": results}]})


class TestParsePsalmSarif:
    """Tests for basic SARIF parsing and filtering."""

    def test_extracts_taint_finding(self) -> None:
        sarif = _make_sarif([_taint_result()])
        result = parse_psalm_sarif_string(sarif)

        assert result["summary"]["total_findings"] == 1
        finding = result["findings"][0]
        assert finding["rule_id"] == "TaintedSql"
        assert finding["severity"] == "high"
        assert finding["message"] == "Tainted SQL detected"
        assert finding["file_path"] == "app.php"
        assert finding["line_start"] == 10

    def test_filters_non_taint_rules(self) -> None:
        non_taint_result = {
            "ruleId": "UnusedVariable",
            "level": "warning",
            "message": {"text": "Unused variable"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "app.php"},
                        "region": {"startLine": 5},
                    }
                }
            ],
        }
        sarif = _make_sarif(
            [_taint_result(), non_taint_result, _taint_result("TaintedHtml")]
        )
        result = parse_psalm_sarif_string(sarif)

        assert result["summary"]["total_findings"] == 2
        rule_ids = [f["rule_id"] for f in result["findings"]]
        assert "UnusedVariable" not in rule_ids
        assert "TaintedSql" in rule_ids
        assert "TaintedHtml" in rule_ids

    def test_summary_total(self) -> None:
        results = [
            _taint_result("TaintedSql", "error"),
            _taint_result("TaintedHtml", "warning"),
            _taint_result("TaintedShell", "error"),
        ]
        sarif = _make_sarif(results)
        result = parse_psalm_sarif_string(sarif)

        assert result["summary"]["total_findings"] == 3

    def test_empty_results(self) -> None:
        sarif = _make_sarif([])
        result = parse_psalm_sarif_string(sarif)

        assert result["summary"]["total_findings"] == 0
        assert result["findings"] == []

    def test_invalid_json_returns_error(self) -> None:
        result = parse_psalm_sarif_string("not valid json")
        assert "error" in result
        assert "JSON parse error" in result["error"]

    def test_file_not_found_returns_error(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "nonexistent.json"
        result = parse_psalm_sarif(missing_file)
        assert "error" in result
        assert "JSON parse error" in result["error"]


class TestSeverityMapping:
    """Tests for severity level mapping."""

    @pytest.mark.parametrize(
        "level,expected",
        [
            ("error", "high"),
            ("warning", "medium"),
            ("note", "low"),
        ],
    )
    def test_severity_mapping(self, level: str, expected: str) -> None:
        sarif = _make_sarif([_taint_result(level=level)])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["severity"] == expected

    def test_missing_level_defaults_to_high(self) -> None:
        result_dict = _taint_result()
        del result_dict["level"]
        sarif = _make_sarif([result_dict])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["severity"] == "high"


class TestCWEMapping:
    """Tests for CWE mapping from rule IDs."""

    @pytest.mark.parametrize(
        "rule_id,expected_cwe",
        [
            ("TaintedSql", "CWE-89"),
            ("TaintedHtml", "CWE-79"),
            ("TaintedShell", "CWE-78"),
            ("TaintedInclude", "CWE-98"),
            ("TaintedEval", "CWE-95"),
            ("TaintedSSRF", "CWE-918"),
            ("TaintedFile", "CWE-73"),
            ("TaintedHeader", "CWE-113"),
            ("TaintedLdap", "CWE-90"),
            ("TaintedUnserialize", "CWE-502"),
            ("TaintedCallable", "CWE-470"),
            ("TaintedCookie", "CWE-614"),
            ("TaintedUserSecret", "CWE-200"),
            ("TaintedSystemSecret", "CWE-200"),
        ],
    )
    def test_cwe_mapping(self, rule_id: str, expected_cwe: str) -> None:
        sarif = _make_sarif([_taint_result(rule_id=rule_id)])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["cwe"] == expected_cwe

    def test_unknown_rule_id_empty_cwe(self) -> None:
        sarif = _make_sarif([_taint_result(rule_id="TaintedUnknown")])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["cwe"] == ""


class TestTaintFlowExtraction:
    """Tests for taint flow extraction and path tracking."""

    def test_extracts_flow_steps(self) -> None:
        sarif = _make_sarif([_taint_result()])
        result = parse_psalm_sarif_string(sarif)
        finding = result["findings"][0]

        assert len(finding["taint_flow"]) == 3
        assert finding["taint_source"] == "$untrusted_input"
        assert finding["taint_sink"] == "$db->execute()"

        assert finding["taint_flow"][0]["text"] == "$untrusted_input"
        assert finding["taint_flow"][0]["line"] == 10
        assert finding["taint_flow"][1]["text"] == "$query"
        assert finding["taint_flow"][1]["line"] == 11
        assert finding["taint_flow"][2]["text"] == "$db->execute()"
        assert finding["taint_flow"][2]["line"] == 12

    def test_taint_type_extracted_from_rule_id(self) -> None:
        test_cases = [
            ("TaintedSql", "sql"),
            ("TaintedHtml", "html"),
            ("TaintedShell", "shell"),
            ("TaintedSSRF", "ssrf"),
        ]
        for rule_id, expected_type in test_cases:
            sarif = _make_sarif([_taint_result(rule_id=rule_id)])
            result = parse_psalm_sarif_string(sarif)
            assert result["findings"][0]["taint_type"] == expected_type

    def test_empty_code_flows(self) -> None:
        sarif = _make_sarif([_taint_result(code_flow=False)])
        result = parse_psalm_sarif_string(sarif)
        finding = result["findings"][0]

        assert finding["taint_flow"] == []
        assert finding["taint_source"] == ""
        assert finding["taint_sink"] == ""

    def test_single_flow_step_source_is_sink(self) -> None:
        result_dict = _taint_result()
        result_dict["codeFlows"][0]["threadFlows"][0]["locations"] = [
            {
                "location": {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "app.php"},
                        "region": {"startLine": 10},
                    },
                    "message": {"text": "$value"},
                }
            }
        ]
        sarif = _make_sarif([result_dict])
        result = parse_psalm_sarif_string(sarif)
        finding = result["findings"][0]

        assert len(finding["taint_flow"]) == 1
        assert finding["taint_source"] == "$value"
        assert finding["taint_sink"] == "$value"


class TestLocationExtraction:
    """Tests for location and region data extraction."""

    def test_extracts_column_start_when_present(self) -> None:
        sarif = _make_sarif([_taint_result(col=5)])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["col_start"] == 5

    def test_col_start_none_when_absent(self) -> None:
        sarif = _make_sarif([_taint_result()])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["col_start"] is None

    def test_extracts_end_line_when_present(self) -> None:
        sarif = _make_sarif([_taint_result(end_line=15)])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["line_end"] == 15

    def test_line_end_none_when_absent(self) -> None:
        sarif = _make_sarif([_taint_result()])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["line_end"] is None


class TestConfidenceAndDefaults:
    """Tests for confidence level and default values."""

    def test_confidence_always_confirmed(self) -> None:
        sarif = _make_sarif([_taint_result()])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["confidence"] == "confirmed"

    def test_missing_locations_uses_defaults(self) -> None:
        result_dict = {
            "ruleId": "TaintedSql",
            "level": "error",
            "message": {"text": "SQL injection"},
            "locations": [],
        }
        sarif = _make_sarif([result_dict])
        result = parse_psalm_sarif_string(sarif)
        finding = result["findings"][0]

        assert finding["file_path"] == ""
        assert finding["line_start"] == 0
        assert finding["col_start"] is None
        assert finding["line_end"] is None


class TestBySeveritySummary:
    """Tests for by_severity breakdown in summary."""

    def test_by_severity_breakdown(self) -> None:
        results = [
            _taint_result("TaintedSql", "error"),
            _taint_result("TaintedHtml", "error"),
            _taint_result("TaintedShell", "warning"),
            _taint_result("TaintedFile", "note"),
        ]
        sarif = _make_sarif(results)
        result = parse_psalm_sarif_string(sarif)

        by_sev = result["summary"]["by_severity"]
        assert by_sev["high"] == 2
        assert by_sev["medium"] == 1
        assert by_sev["low"] == 1

    def test_by_severity_empty_when_no_findings(self) -> None:
        sarif = _make_sarif([])
        result = parse_psalm_sarif_string(sarif)
        assert result["summary"]["by_severity"] == {}


class TestEdgeCases:
    """Tests for edge cases and unusual but valid inputs."""

    def test_empty_runs_array(self) -> None:
        sarif = json.dumps({"runs": []})
        result = parse_psalm_sarif_string(sarif)
        assert result["summary"]["total_findings"] == 0
        assert result["findings"] == []

    def test_missing_runs_key(self) -> None:
        sarif = json.dumps({})
        result = parse_psalm_sarif_string(sarif)
        assert result["summary"]["total_findings"] == 0
        assert result["findings"] == []

    def test_parse_from_file(self, tmp_path: Path) -> None:
        sarif_file = tmp_path / "output.sarif"
        sarif_file.write_text(_make_sarif([_taint_result()]))

        result = parse_psalm_sarif(sarif_file)
        assert result["summary"]["total_findings"] == 1
        assert result["findings"][0]["rule_id"] == "TaintedSql"

    def test_message_as_string_not_object(self) -> None:
        result_dict = _taint_result()
        result_dict["message"] = "Simple string message"
        sarif = _make_sarif([result_dict])
        result = parse_psalm_sarif_string(sarif)
        assert result["findings"][0]["message"] == ""
