"""Unit tests for Antares CWE localization parser and handler."""

import json

import pytest

from domain.tools.base import ToolResult
from infrastructure.tools.parsers.antares import (
    AntaresHandler,
    parse_antares_json_string,
)


@pytest.fixture
def antares_handler() -> AntaresHandler:
    """Provide an AntaresHandler instance."""
    return AntaresHandler()


@pytest.fixture
def sample_json_output() -> str:
    """Provide sample Antares JSON output."""
    return json.dumps(
        {
            "summary": {
                "total_findings": 3,
                "tool_call_count": 45,
                "duration_seconds": 120.5,
                "cwe_ids_triggered": ["CWE-78", "CWE-502"],
                "failed_tool_calls": 2,
                "retried_turns": 1,
                "generation_errors": 0,
                "failed_workers": 0,
                "total_workers": 5,
                "incomplete_reason": None,
            },
            "findings": [
                {
                    "title": "Potential OS command injection via subprocess call",
                    "file_path": "src/utils/runner.py",
                    "cwe_ids": ["CWE-78"],
                    "submission_rank": 1,
                    "likelihood_of_exploit": "High",
                },
                {
                    "title": "Unsafe deserialization of user-supplied data",
                    "file_path": "src/api/handlers.py",
                    "cwe_ids": ["CWE-502"],
                    "submission_rank": 1,
                    "likelihood_of_exploit": "Medium",
                },
                {
                    "title": "Secondary command injection surface",
                    "file_path": "src/workers/dispatch.py",
                    "cwe_ids": ["CWE-78", "CWE-77"],
                    "submission_rank": 2,
                    "likelihood_of_exploit": "High",
                },
            ],
            "per_cwe_results": [
                {
                    "cwe_id": "CWE-78",
                    "finding_count": 2,
                    "tool_call_count": 15,
                    "duration_seconds": 45.2,
                    "error_message": None,
                    "failed_tool_calls": 1,
                    "retried_turns": 0,
                },
                {
                    "cwe_id": "CWE-502",
                    "finding_count": 1,
                    "tool_call_count": 12,
                    "duration_seconds": 38.7,
                    "error_message": None,
                    "failed_tool_calls": 0,
                    "retried_turns": 1,
                },
                {
                    "cwe_id": "CWE-89",
                    "finding_count": 0,
                    "tool_call_count": 15,
                    "duration_seconds": 36.6,
                    "error_message": None,
                    "failed_tool_calls": 1,
                    "retried_turns": 0,
                },
            ],
            "metadata": {
                "schema_version": "1.0",
                "request_id": "abc123",
                "mode": "sweep",
                "model": "granite-3.0-1b",
                "target": "/path/to/repo",
            },
            "warnings": [],
        }
    )


class TestParseAntaresJson:
    """Tests for parse_antares_json_string function."""

    def test_parse_json_finding_count(self, sample_json_output: str) -> None:
        """Verify parser extracts all findings."""
        result = parse_antares_json_string(sample_json_output)
        findings = result.get("findings", [])
        assert len(findings) == 3

    def test_parse_json_summary(self, sample_json_output: str) -> None:
        """Verify summary fields are present in parsed data."""
        result = parse_antares_json_string(sample_json_output)
        summary = result.get("summary", {})
        assert summary.get("total_findings") == 3
        assert "by_severity" in summary
        assert "files_scanned" in summary

    def test_parse_json_per_cwe_results(self, sample_json_output: str) -> None:
        """Verify per-CWE results are preserved."""
        result = parse_antares_json_string(sample_json_output)
        per_cwe = result.get("per_cwe_results", [])
        assert len(per_cwe) == 3
        assert per_cwe[0]["cwe_id"] == "CWE-78"
        assert per_cwe[0]["tool_call_count"] == 15

    def test_parse_json_error_on_invalid(self) -> None:
        """Verify parser returns error dict on invalid JSON."""
        result = parse_antares_json_string("not valid json")
        assert "error" in result
        assert "JSON parse error" in result["error"]
        assert result.get("raw_output") == "not valid json"


class TestAntaresHandlerAttributes:
    """Tests for AntaresHandler class attributes."""

    def test_handler_implements_protocol(self, antares_handler: AntaresHandler) -> None:
        """Verify handler has required attributes per ToolHandler protocol."""
        assert antares_handler.tool_name == "antares"
        assert antares_handler.domain == "code"
        assert antares_handler.segment == "sast"
        assert antares_handler.should_enrich is True
        assert antares_handler.should_visualize is True
        assert "severity" in antares_handler.non_enriched_fields
        assert "weakness" in antares_handler.type_flags
        assert "type_weakness" in antares_handler.type_flags["weakness"]
        assert all(
            f in antares_handler.normalized_fields
            for f in [
                "confidence",
                "cwe",
                "file_path",
                "finding_type",
                "rule_id",
                "severity",
            ]
        )
        assert len(antares_handler.enrichment_fields) > 0
        field_names = {spec.field_name for spec in antares_handler.enrichment_fields}
        assert all(
            f in field_names
            for f in ["risk_type", "remediation", "confidence", "owasp_name", "title"]
        )


class TestAntaresHandlerNormalize:
    """Tests for AntaresHandler.normalize method."""

    def test_normalize_row_count(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify normalize produces one row per finding."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        assert len(rows) == 3

    @pytest.mark.parametrize(
        "likelihood_value,expected_severity,min_count",
        [
            ("High", "high", 2),
            ("Medium", "medium", 1),
        ],
    )
    def test_severity_mapping(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
        likelihood_value: str,
        expected_severity: str,
        min_count: int,
    ) -> None:
        """Verify likelihood values map to expected severity."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        matching_rows = [r for r in rows if r.get("severity") == expected_severity]
        assert len(matching_rows) >= min_count

    def test_confidence_always_potential(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify all rows have confidence set to potential."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        for row in rows:
            assert row.get("confidence") == "potential"

    def test_finding_type_weakness(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify all rows have finding_type set to weakness."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        for row in rows:
            finding_type = row.get("finding_type")
            assert finding_type == json.dumps(["weakness"])

    def test_cwe_list_preserved(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify multi-CWE findings preserve full list."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        # Third finding has CWE-78 and CWE-77
        multi_cwe_row = rows[2]
        cwe_str = multi_cwe_row.get("cwe", "[]")
        cwe_list = json.loads(cwe_str)
        assert "CWE-78" in cwe_list
        assert "CWE-77" in cwe_list

    def test_rule_id_is_primary_cwe(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify rule_id is set to primary (first) CWE."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        assert rows[0].get("rule_id") == "CWE-78"
        assert rows[1].get("rule_id") == "CWE-502"
        assert rows[2].get("rule_id") == "CWE-78"

    def test_meta_includes_submission_rank(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify meta dict includes submission_rank."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        for row in rows:
            meta_str = row.get("meta", "{}")
            meta = json.loads(meta_str)
            assert "submission_rank" in meta

    def test_meta_includes_per_cwe_stats(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify meta dict includes per-CWE statistics."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        # First row is CWE-78 which has per_cwe_results
        meta_str = rows[0].get("meta", "{}")
        meta = json.loads(meta_str)
        assert "cwe_tool_calls" in meta
        assert meta["cwe_tool_calls"] == 15

    def test_domain_and_segment_in_row(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify domain and segment are included in rows."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        for row in rows:
            assert row.get("domain") == "code"
            assert row.get("segment") == "sast"

    def test_type_weakness_flag_set(
        self,
        antares_handler: AntaresHandler,
        sample_json_output: str,
    ) -> None:
        """Verify type_weakness flag is True."""
        parsed = parse_antares_json_string(sample_json_output)
        result = ToolResult(
            tool_name="antares",
            success=True,
            output=sample_json_output,
            parsed_data=parsed,
            output_files={},
            timestamp="2025-07-27T12:00:00+00:00",
            duration_seconds=120.5,
        )
        rows = antares_handler.normalize(result, "default")
        for row in rows:
            assert row.get("type_weakness") is True


class TestAntaresHandlerRender:
    """Tests for AntaresHandler.render method."""

    def test_render_format(self, antares_handler: AntaresHandler) -> None:
        """Verify render output starts with [antares]."""
        row = {
            "rule_id": "CWE-78",
            "file_path": "src/utils/runner.py",
            "severity": "high",
            "description": "Command injection",
        }
        output = antares_handler.render(row)
        assert output.startswith("[antares]")

    def test_render_includes_cwe(self, antares_handler: AntaresHandler) -> None:
        """Verify render includes CWE."""
        row = {
            "rule_id": "CWE-78",
            "file_path": "src/utils/runner.py",
            "severity": "high",
            "description": "Command injection",
        }
        output = antares_handler.render(row)
        assert "CWE-78" in output

    def test_render_includes_file_path(self, antares_handler: AntaresHandler) -> None:
        """Verify render includes file path."""
        row = {
            "rule_id": "CWE-78",
            "file_path": "src/utils/runner.py",
            "severity": "high",
        }
        output = antares_handler.render(row)
        assert "src/utils/runner.py" in output

    def test_render_includes_severity(self, antares_handler: AntaresHandler) -> None:
        """Verify render includes severity."""
        row = {
            "rule_id": "CWE-78",
            "file_path": "src/utils/runner.py",
            "severity": "high",
        }
        output = antares_handler.render(row)
        assert "high" in output


class TestAntaresHandlerFingerprintKey:
    """Tests for AntaresHandler.fingerprint_key method."""

    def test_fingerprint_key_format(self, antares_handler: AntaresHandler) -> None:
        """Verify fingerprint_key format is correct."""
        finding = {
            "cwe": json.dumps(["CWE-78"]),
            "file_path": "src/utils/runner.py",
        }
        key = antares_handler.fingerprint_key(finding)
        assert key == "antares|CWE-78|src/utils/runner.py"

    def test_fingerprint_stable(self, antares_handler: AntaresHandler) -> None:
        """Verify same inputs produce same fingerprint key."""
        finding = {
            "cwe": json.dumps(["CWE-502"]),
            "file_path": "src/api/handlers.py",
        }
        key1 = antares_handler.fingerprint_key(finding)
        key2 = antares_handler.fingerprint_key(finding)
        assert key1 == key2

    def test_fingerprint_uses_primary_cwe(
        self, antares_handler: AntaresHandler
    ) -> None:
        """Verify fingerprint uses primary (first) CWE."""
        finding = {
            "cwe": json.dumps(["CWE-78", "CWE-77"]),
            "file_path": "src/workers/dispatch.py",
        }
        key = antares_handler.fingerprint_key(finding)
        assert "CWE-78" in key
        assert "CWE-77" not in key

    def test_fingerprint_with_empty_cwe_list(
        self, antares_handler: AntaresHandler
    ) -> None:
        """Verify fingerprint handles empty CWE list."""
        finding = {
            "cwe": json.dumps([]),
            "file_path": "src/test.py",
        }
        key = antares_handler.fingerprint_key(finding)
        assert "antares||src/test.py" == key
