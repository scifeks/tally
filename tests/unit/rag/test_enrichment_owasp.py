"""Unit tests for owasp_name enrichment. Native Semgrep mapping and validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from application.rag.enrichment import EnrichmentPipeline
from domain.tools.base import ToolResult
from infrastructure.tools.parsers.semgrep import SemgrepHandler


def _make_semgrep_result(owasp: object = None) -> ToolResult:
    finding: dict = {
        "rule_id": "python.lang.security.audit.exec-use",
        "severity": "high",
        "message": "Use of exec()",
        "file_path": "app.py",
        "line_start": 10,
        "line_end": 10,
        "code_snippet": "exec(user_input)",
    }
    if owasp is not None:
        finding["owasp"] = owasp
    return ToolResult(
        tool_name="semgrep",
        success=True,
        output="",
        parsed_data={"findings": [finding], "summary": {}},
        output_files={},
        timestamp="2024-01-01T00:00:00",
        duration_seconds=0.1,
    )


def _chunks(result: ToolResult) -> list[dict]:
    return SemgrepHandler().normalize(result, "default")


def _pipeline() -> EnrichmentPipeline:
    return EnrichmentPipeline(finding_repo=MagicMock())


# Native Semgrep mapping


class TestSemgrepNativeMapping:
    def test_bare_code_maps_to_name(self) -> None:
        meta = _chunks(_make_semgrep_result("A03:2021"))[0]
        names = json.loads(meta["owasp_name"])
        assert isinstance(names, list)
        assert len(names) >= 1
        assert all(isinstance(n, str) and n for n in names)

    def test_code_plus_label_stripped_to_code(self) -> None:
        # "A03:2021 - Injection" should resolve to the same name as bare "A03:2021"
        bare = _chunks(_make_semgrep_result("A03:2021"))[0]
        labeled = _chunks(_make_semgrep_result("A03:2021 - Injection"))[0]
        assert bare["owasp_name"] == labeled["owasp_name"]

    def test_2025_code_maps_to_nonempty_name(self) -> None:
        meta = _chunks(_make_semgrep_result("A01:2025"))[0]
        names = json.loads(meta["owasp_name"])
        assert isinstance(names, list)
        assert len(names) >= 1
        assert all(isinstance(n, str) and n for n in names)

    def test_2017_code_maps_to_nonempty_name(self) -> None:
        meta = _chunks(_make_semgrep_result("A7:2017"))[0]
        names = json.loads(meta["owasp_name"])
        assert isinstance(names, list)
        assert len(names) >= 1
        assert all(isinstance(n, str) and n for n in names)

    def test_list_of_codes_returns_multiple_names(self) -> None:
        meta = _chunks(_make_semgrep_result(["A03:2021", "A01:2021"]))[0]
        names = json.loads(meta["owasp_name"])
        assert isinstance(names, list)
        assert len(names) == 2
        assert all(isinstance(n, str) and n for n in names)

    def test_partial_list_keeps_only_mapped(self) -> None:
        meta = _chunks(_make_semgrep_result(["A03:2021", "UNKNOWN"]))[0]
        names = json.loads(meta["owasp_name"])
        assert len(names) == 1
        assert all(isinstance(n, str) and n for n in names)

    def test_unknown_code_omits_owasp_name(self) -> None:
        meta = _chunks(_make_semgrep_result("BADCODE"))[0]
        assert "owasp_name" not in meta

    def test_absent_owasp_omits_owasp_name(self) -> None:
        meta = _chunks(_make_semgrep_result())[0]
        assert "owasp_name" not in meta

    def test_all_unknown_list_omits_owasp_name(self) -> None:
        meta = _chunks(_make_semgrep_result(["UNKNOWN1", "UNKNOWN2"]))[0]
        assert "owasp_name" not in meta

    def test_duplicate_codes_deduplicated(self) -> None:
        meta = _chunks(_make_semgrep_result(["A03:2021", "A03:2021"]))[0]
        names = json.loads(meta["owasp_name"])
        assert len(names) == len(set(names))

    def test_cross_edition_same_name_deduplicated(self) -> None:
        # Two codes that map to the same name should yield one entry
        meta = _chunks(_make_semgrep_result(["A01:2021", "A5:2017"]))[0]
        names = json.loads(meta["owasp_name"])
        assert len(names) == len(set(names))

    def test_owasp_name_is_valid_json(self) -> None:
        meta = _chunks(_make_semgrep_result("A03:2021"))[0]
        # Must not raise
        parsed = json.loads(meta["owasp_name"])
        assert isinstance(parsed, list)


# Enrichment pipeline: owasp_name in fields_to_enrich


class TestGetFieldsToEnrich:
    def test_semgrep_without_owasp_includes_owasp_name(self) -> None:
        pipeline = _pipeline()
        meta = {
            "tool": "semgrep",
            "severity": "high",
            "confidence": "probable",
            "risk_type": "exec_injection",
            "remediation": "Do not use exec.",
            "description": "Use of exec()",
        }
        fields = pipeline._get_fields_to_enrich(meta)
        assert "owasp_name" in fields

    def test_semgrep_with_native_owasp_name_skips_enrichment(self) -> None:
        pipeline = _pipeline()
        meta = {
            "tool": "semgrep",
            "severity": "high",
            "confidence": "probable",
            "risk_type": "exec_injection",
            "remediation": "Do not use exec.",
            "description": "Use of exec()",
            "owasp_name": json.dumps(["Injection"]),
        }
        fields = pipeline._get_fields_to_enrich(meta)
        assert "owasp_name" not in fields

    def test_gitleaks_returns_no_fields(self) -> None:
        pipeline = _pipeline()
        meta = {"tool": "gitleaks", "severity": "high"}
        fields = pipeline._get_fields_to_enrich(meta)
        assert fields == []

    def test_nmap_returns_no_fields(self) -> None:
        pipeline = _pipeline()
        meta = {"tool": "nmap", "severity": "informational"}
        fields = pipeline._get_fields_to_enrich(meta)
        assert fields == []

    def test_zap_includes_owasp_name(self) -> None:
        pipeline = _pipeline()
        meta = {
            "tool": "zap",
            "severity": "high",
            "confidence": "probable",
            "risk_type": "SQL Injection",
            "remediation": "Use parameterised queries.",
            "description": "SQL injection in login form.",
        }
        fields = pipeline._get_fields_to_enrich(meta)
        assert "owasp_name" in fields


# Enrichment pipeline: _validate_response


class TestValidateResponseOwaspName:
    def test_valid_owasp_name_accepted(self) -> None:
        pipeline = _pipeline()
        result = pipeline._validate_response(
            {"owasp_name": "Injection"}, ["owasp_name"]
        )
        assert result["owasp_name"] == "Injection"

    def test_valid_name_with_parens_accepted(self) -> None:
        pipeline = _pipeline()
        result = pipeline._validate_response(
            {"owasp_name": "Server-Side Request Forgery (SSRF)"}, ["owasp_name"]
        )
        assert result["owasp_name"] == "Server-Side Request Forgery (SSRF)"

    def test_invalid_owasp_name_rejected(self) -> None:
        pipeline = _pipeline()
        result = pipeline._validate_response(
            {"owasp_name": "Made Up Category"}, ["owasp_name"]
        )
        assert "owasp_name" not in result

    def test_owasp_code_rejected(self) -> None:
        """LLM should return the Name, not the code; reject codes."""
        pipeline = _pipeline()
        result = pipeline._validate_response({"owasp_name": "A03:2021"}, ["owasp_name"])
        assert "owasp_name" not in result

    def test_null_owasp_name_dropped(self) -> None:
        """LLM returns null → json.loads gives None → isinstance(val, str) fails."""
        pipeline = _pipeline()
        result = pipeline._validate_response({"owasp_name": None}, ["owasp_name"])
        assert "owasp_name" not in result

    def test_empty_string_dropped(self) -> None:
        pipeline = _pipeline()
        result = pipeline._validate_response({"owasp_name": ""}, ["owasp_name"])
        assert "owasp_name" not in result

    def test_unrequested_owasp_name_ignored(self) -> None:
        pipeline = _pipeline()
        result = pipeline._validate_response({"owasp_name": "Injection"}, ["risk_type"])
        assert "owasp_name" not in result

    @pytest.mark.parametrize(
        "name",
        [
            "Broken Access Control",
            "Security Misconfiguration",
            "Software Supply Chain Failures",
            "Cryptographic Failures",
            "Injection",
            "Insecure Design",
            "Authentication Failures",
            "Software or Data Integrity Failures",
            "Security Logging and Alerting Failures",
            "Mishandling of Exceptional Conditions",
            "Vulnerable and Outdated Components",
            "Identification and Authentication Failures",
            "Software and Data Integrity Failures",
            "Security Logging and Monitoring Failures",
            "Server-Side Request Forgery (SSRF)",
            "Broken Authentication",
            "Sensitive Data Exposure",
            "XML External Entities (XXE)",
            "Cross-Site Scripting (XSS)",
            "Insecure Deserialization",
            "Using Components with Known Vulnerabilities",
            "Insufficient Logging and Monitoring",
        ],
    )
    def test_all_valid_names_accepted(self, name: str) -> None:
        pipeline = _pipeline()
        result = pipeline._validate_response({"owasp_name": name}, ["owasp_name"])
        assert result.get("owasp_name") == name
