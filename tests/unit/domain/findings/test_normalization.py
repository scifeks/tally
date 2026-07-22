"""Unit tests for domain.findings.normalization."""

from __future__ import annotations

import json
import logging

import pytest

from domain.findings.normalization import (
    NormalizedFinding,
    build_triage_meta,
    normalise_cwe,
    normalise_finding_for_insert,
    normalise_finding_type,
    prepare_row_for_render,
    severity_to_rank,
    split_analyst_fields,
    split_enrichment_fields,
)


class TestSeverityToRank:
    @pytest.mark.parametrize(
        ("label", "expected_rank"),
        [
            ("critical", 0),
            ("high", 1),
            ("medium", 2),
            ("low", 3),
            ("informational", 4),
            ("CRITICAL", 0),
            ("High", 1),
        ],
    )
    def test_valid_label(self, label: str, expected_rank: int) -> None:
        assert severity_to_rank(label) == expected_rank

    def test_none_input(self) -> None:
        assert severity_to_rank(None) is None

    def test_invalid_label(self) -> None:
        assert severity_to_rank("unknown") is None
        assert severity_to_rank("") is None

    def test_non_string_coercible(self) -> None:
        assert severity_to_rank({}) is None


class TestNormaliseCwe:
    def test_none_input(self) -> None:
        assert normalise_cwe(None) is None

    def test_int_positive(self) -> None:
        result = normalise_cwe(89)
        assert result == json.dumps(["CWE-89"])

    def test_int_zero(self) -> None:
        assert normalise_cwe(0) is None

    def test_int_negative(self) -> None:
        assert normalise_cwe(-1) is None

    def test_list_of_ints(self) -> None:
        result = normalise_cwe([89, 90])
        assert result == json.dumps(["89", "90"])

    def test_list_with_empty_values(self) -> None:
        result = normalise_cwe([89, None, 90])
        assert result == json.dumps(["89", "90"])

    def test_list_all_empty(self) -> None:
        result = normalise_cwe([None, ""])
        assert result == json.dumps([])

    def test_json_string_passthrough(self) -> None:
        json_str = json.dumps(["CWE-89", "CWE-90"])
        assert normalise_cwe(json_str) == json_str

    def test_comma_separated_string(self) -> None:
        result = normalise_cwe("89, 90, 91")
        assert result == json.dumps(["89", "90", "91"])

    def test_comma_separated_with_whitespace(self) -> None:
        result = normalise_cwe("  89  ,  90  ")
        assert result == json.dumps(["89", "90"])

    def test_comma_separated_empty_parts(self) -> None:
        result = normalise_cwe("89,,90")
        assert result == json.dumps(["89", "90"])

    def test_comma_separated_all_empty(self) -> None:
        assert normalise_cwe(",,") is None


class TestNormaliseFindingType:
    def test_none_input(self) -> None:
        assert normalise_finding_type(None) is None

    def test_valid_string(self) -> None:
        result = normalise_finding_type("secret")
        assert result == json.dumps(["secret"])

    def test_valid_string_case_sensitive(self) -> None:
        result = normalise_finding_type("vulnerability")
        assert result == json.dumps(["vulnerability"])

    def test_invalid_string_returns_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            result = normalise_finding_type("invalid_type")
        assert result is None
        assert "Invalid finding_type value" in caplog.text

    def test_list_of_valid_strings(self) -> None:
        result = normalise_finding_type(["secret", "vulnerability"])
        assert result is not None
        parsed = json.loads(result)
        assert set(parsed) == {"secret", "vulnerability"}

    def test_list_with_invalid_strings(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = normalise_finding_type(["secret", "invalid", "weakness"])
        assert result is not None
        parsed = json.loads(result)
        assert set(parsed) == {"secret", "weakness"}
        assert "Invalid finding_type value" in caplog.text

    def test_list_all_invalid(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = normalise_finding_type(["invalid1", "invalid2"])
        assert result is None
        assert "Invalid finding_type value" in caplog.text

    def test_json_string_valid(self) -> None:
        json_str = json.dumps(["secret", "vulnerability"])
        result = normalise_finding_type(json_str)
        assert result == json_str

    def test_json_string_invalid_json_becomes_literal(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            result = normalise_finding_type("[not valid json")
        assert result is None

    def test_json_string_with_invalid_types(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        json_str = json.dumps(["secret", "invalid"])
        with caplog.at_level(logging.WARNING):
            result = normalise_finding_type(json_str)
        assert result is not None
        parsed = json.loads(result)
        assert parsed == ["secret"]

    def test_non_string_coerced(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            result = normalise_finding_type(123)
        assert result is None
        assert "Invalid finding_type value" in caplog.text


class TestNormaliseFindingForInsert:
    def test_basic_raw_finding(self) -> None:
        raw = {
            "tool": "dalfox",
            "domain": "web",
            "severity": "high",
            "finding_type": "vulnerability",
            "file_path": "index.php",
            "description": "XSS vulnerability",
        }
        result = normalise_finding_for_insert(raw)
        assert isinstance(result, NormalizedFinding)
        assert result.columns["tool"] == "dalfox"
        assert result.columns["domain"] == "web"
        assert result.columns["severity"] == 1  # high
        assert result.columns["finding_type"] == json.dumps(["vulnerability"])
        assert result.columns["file"] == "index.php"
        assert result.columns["description"] == "XSS vulnerability"

    def test_file_aliasing_priority(self) -> None:
        raw = {
            "file_path": "path/file.py",
            "lockfile": "requirements.txt",
            "file": "old.txt",
        }
        result = normalise_finding_for_insert(raw)
        assert result.columns["file"] == "path/file.py"

    def test_file_aliasing_fallback_to_lockfile(self) -> None:
        raw = {
            "lockfile": "requirements.txt",
            "file": "old.txt",
        }
        result = normalise_finding_for_insert(raw)
        assert result.columns["file"] == "requirements.txt"

    def test_file_aliasing_fallback_to_file(self) -> None:
        raw = {"file": "old.txt"}
        result = normalise_finding_for_insert(raw)
        assert result.columns["file"] == "old.txt"

    def test_no_severity_columns(self) -> None:
        raw = {"tool": "dalfox"}
        result = normalise_finding_for_insert(raw)
        assert result.columns["severity"] is None

    def test_comma_list_fields_split(self) -> None:
        raw = {
            "tool": "dalfox",
            "technology": "PHP, JavaScript, HTML",
            "tags": "xss, web, critical",
        }
        result = normalise_finding_for_insert(raw)
        assert result.meta["technology"] == ["PHP", "JavaScript", "HTML"]
        assert result.meta["tags"] == ["xss", "web", "critical"]

    def test_comma_list_fields_with_empty_parts(self) -> None:
        raw = {"tool": "dalfox", "tags": "xss,,web"}
        result = normalise_finding_for_insert(raw)
        assert result.meta["tags"] == ["xss", "web"]

    def test_extra_keys_go_to_meta(self) -> None:
        raw = {
            "tool": "dalfox",
            "domain": "web",
            "custom_field": "custom_value",
            "extra": "data",
        }
        result = normalise_finding_for_insert(raw)
        assert result.meta["custom_field"] == "custom_value"
        assert result.meta["extra"] == "data"

    def test_cwe_normalized(self) -> None:
        raw = {"tool": "dalfox", "cwe": 89}
        result = normalise_finding_for_insert(raw)
        assert result.columns["cwe"] == json.dumps(["CWE-89"])

    def test_cwe_id_fallback(self) -> None:
        raw = {"tool": "dalfox", "cwe_id": 90}
        result = normalise_finding_for_insert(raw)
        assert result.columns["cwe"] == json.dumps(["CWE-90"])

    def test_cwe_ids_fallback(self) -> None:
        raw = {"tool": "dalfox", "cwe_ids": [89, 90]}
        result = normalise_finding_for_insert(raw)
        assert result.columns["cwe"] == json.dumps(["89", "90"])

    def test_cwe_priority_order(self) -> None:
        raw = {
            "tool": "dalfox",
            "cwe": 89,
            "cwe_id": 90,
            "cwe_ids": [91],
        }
        result = normalise_finding_for_insert(raw)
        assert result.columns["cwe"] == json.dumps(["CWE-89"])

    def test_direct_columns_copied(self) -> None:
        raw = {
            "tool": "dalfox",
            "domain": "web",
            "segment": "web",
            "confidence": "confirmed",
            "rule_id": "rule_123",
            "url": "http://example.com",
            "vulnerability_id": "CVE-2021-123",
            "package_name": "lodash",
            "ecosystem": "npm",
            "description": "A finding",
            "package_version": "1.0.0",
        }
        result = normalise_finding_for_insert(raw)
        for key in [
            "tool",
            "domain",
            "segment",
            "confidence",
            "rule_id",
            "url",
            "vulnerability_id",
            "package_name",
            "ecosystem",
            "description",
            "package_version",
        ]:
            assert result.columns[key] == raw[key]

    def test_finding_type_none_not_added_to_columns(self) -> None:
        raw = {"tool": "dalfox", "finding_type": "invalid"}
        result = normalise_finding_for_insert(raw)
        assert result.columns["finding_type"] is None


class TestSplitAnalystFields:
    def test_analyst_meta_keys_routed_to_meta(self) -> None:
        fields = {
            "remediation": "patch",
            "risk_type": "vulnerability",
            "owasp_name": "Injection",
            "title": "SQL Injection",
            "tags": "sql, injection",
            "notes": "critical",
        }
        columns, meta = split_analyst_fields(fields)
        assert columns == {}
        assert meta == fields

    def test_other_fields_routed_to_columns(self) -> None:
        fields = {
            "confidence": "confirmed",
            "severity": "high",
            "custom": "value",
        }
        columns, meta = split_analyst_fields(fields)
        assert meta == {}
        assert columns["confidence"] == "confirmed"
        assert columns["severity"] == 1  # high → rank 1
        assert columns["custom"] == "value"

    def test_severity_converted_to_rank(self) -> None:
        fields = {"severity": "critical"}
        columns, meta = split_analyst_fields(fields)
        assert columns["severity"] == 0

    def test_severity_none_not_converted(self) -> None:
        fields = {"severity": None}
        columns, meta = split_analyst_fields(fields)
        assert "severity" not in columns or columns.get("severity") is None

    def test_severity_invalid_not_converted(self) -> None:
        fields = {"severity": "invalid"}
        columns, meta = split_analyst_fields(fields)
        assert columns["severity"] is None

    def test_mixed_analyst_and_other(self) -> None:
        fields = {
            "remediation": "patch",
            "confidence": "confirmed",
            "severity": "medium",
        }
        columns, meta = split_analyst_fields(fields)
        assert meta == {"remediation": "patch"}
        assert columns["confidence"] == "confirmed"
        assert columns["severity"] == 2


class TestSplitEnrichmentFields:
    def test_enrichment_meta_fields_routed_to_meta(self) -> None:
        fields = {
            "risk_type": "vulnerability",
            "remediation": "patch",
            "owasp_name": "Injection",
            "title": "SQL Injection",
            "tags": "sql",
            "notes": "critical",
        }
        columns, meta = split_enrichment_fields(fields)
        assert meta == fields
        assert columns == {}

    def test_enrichment_column_fields_routed_to_columns(self) -> None:
        fields = {
            "severity": "high",
            "confidence": "confirmed",
            "description": "A finding",
        }
        columns, meta = split_enrichment_fields(fields)
        assert columns["severity"] == 1  # high → rank 1
        assert columns["confidence"] == "confirmed"
        assert columns["description"] == "A finding"
        assert meta == {}

    def test_unknown_fields_dropped(self) -> None:
        fields = {
            "severity": "high",
            "unknown_field": "value",
            "another_unknown": "data",
        }
        columns, meta = split_enrichment_fields(fields)
        assert columns == {"severity": 1}
        assert meta == {}
        assert "unknown_field" not in columns
        assert "unknown_field" not in meta

    def test_severity_converted_to_rank(self) -> None:
        fields = {"severity": "critical"}
        columns, meta = split_enrichment_fields(fields)
        assert columns["severity"] == 0

    def test_severity_none_not_converted(self) -> None:
        fields = {"severity": None}
        columns, meta = split_enrichment_fields(fields)
        assert "severity" not in columns or columns.get("severity") is None

    def test_severity_invalid_not_converted(self) -> None:
        fields = {"severity": "invalid"}
        columns, meta = split_enrichment_fields(fields)
        assert columns["severity"] is None


class TestBuildTriageMeta:
    def test_all_fields_included(self) -> None:
        result = build_triage_meta(
            confidence="high",
            reasoning="Found direct evidence",
            remediation="Apply patch",
            attack_vector="network",
            call_stack="main() -> vulnerable() -> exec()",
        )
        assert result["confidence"] == "high"
        assert result["reasoning"] == "Found direct evidence"
        assert result["remediation"] == "Apply patch"
        assert result["attack_vector"] == "network"
        assert result["call_stack"] == "main() -> vulnerable() -> exec()"

    def test_none_values_included(self) -> None:
        result = build_triage_meta(
            confidence="high",
            reasoning="Some evidence",
            remediation="Patch it",
            attack_vector=None,
            call_stack=None,
        )
        assert result["attack_vector"] is None
        assert result["call_stack"] is None
        assert len(result) == 5

    def test_build_triage_meta_includes_predicates(
        self,
    ) -> None:
        result = build_triage_meta(
            confidence="confirmed",
            reasoning="trace complete",
            remediation="fix it",
            attack_vector="POST /login",
            call_stack='["a.py:1 foo"]',
            access_required="none",
            exploitation_complexity="low",
            user_interaction="none",
        )
        assert result["access_required"] == "none"
        assert result["exploitation_complexity"] == "low"
        assert result["user_interaction"] == "none"


class TestPrepareRowForRender:
    def test_cwe_list_joined_and_aliased(self) -> None:
        row = {"cwe": ["CWE-89", "CWE-79"], "tool": "semgrep"}
        result = prepare_row_for_render(row)
        assert result["cwe"] == "CWE-89, CWE-79"
        assert result["cwe_id"] == "CWE-89, CWE-79"
        assert result["cwe_ids"] == "CWE-89, CWE-79"

    def test_cwe_single_item_list(self) -> None:
        row = {"cwe": ["CWE-89"]}
        result = prepare_row_for_render(row)
        assert result["cwe"] == "CWE-89"
        assert result["cwe_id"] == "CWE-89"
        assert result["cwe_ids"] == "CWE-89"

    def test_cwe_string_passthrough(self) -> None:
        row = {"cwe": "CWE-89"}
        result = prepare_row_for_render(row)
        assert result["cwe"] == "CWE-89"
        assert result["cwe_id"] == "CWE-89"
        assert result["cwe_ids"] == "CWE-89"

    def test_cwe_none_no_aliases(self) -> None:
        row = {"tool": "semgrep"}
        result = prepare_row_for_render(row)
        assert "cwe_id" not in result
        assert "cwe_ids" not in result

    def test_tags_list_joined(self) -> None:
        row = {"tags": ["xss", "web", "critical"]}
        result = prepare_row_for_render(row)
        assert result["tags"] == "xss, web, critical"

    def test_aliases_list_joined(self) -> None:
        row = {"aliases": ["CVE-2023-1234", "GHSA-abcd"]}
        result = prepare_row_for_render(row)
        assert result["aliases"] == "CVE-2023-1234, GHSA-abcd"

    def test_references_list_joined(self) -> None:
        row = {"references": ["http://a.com", "http://b.com"]}
        result = prepare_row_for_render(row)
        assert result["references"] == "http://a.com, http://b.com"

    def test_finding_type_list_joined(self) -> None:
        row = {"finding_type": ["secret", "vulnerability"]}
        result = prepare_row_for_render(row)
        assert result["finding_type"] == "secret, vulnerability"

    def test_string_fields_unchanged(self) -> None:
        row = {"tags": "already a string", "aliases": "single"}
        result = prepare_row_for_render(row)
        assert result["tags"] == "already a string"
        assert result["aliases"] == "single"

    def test_non_list_fields_untouched(self) -> None:
        row = {
            "tool": "gitleaks",
            "severity": "high",
            "rule_id": "generic-api-key",
            "line_number": 42,
        }
        result = prepare_row_for_render(row)
        assert result["tool"] == "gitleaks"
        assert result["severity"] == "high"
        assert result["rule_id"] == "generic-api-key"
        assert result["line_number"] == 42

    def test_does_not_mutate_input(self) -> None:
        row = {"cwe": ["CWE-89"], "tags": ["a", "b"]}
        prepare_row_for_render(row)
        assert row["cwe"] == ["CWE-89"]
        assert row["tags"] == ["a", "b"]
