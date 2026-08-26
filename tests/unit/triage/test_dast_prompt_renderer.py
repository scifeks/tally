"""Unit tests for the DAST prompt renderer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "triage"


@pytest.fixture()
def zap_finding() -> dict[str, Any]:
    return json.loads((FIXTURES / "zap_finding.json").read_text())


@pytest.fixture()
def burp_finding() -> dict[str, Any]:
    return json.loads((FIXTURES / "burp_finding.json").read_text())


class TestDastPromptRenderer:
    def test_zap_finding_renders_all_evidence_fields(
        self, zap_finding: dict[str, Any]
    ) -> None:
        from application.triage.prompts import dast_trace

        result = dast_trace.render(zap_finding, project="demo")
        assert isinstance(result, str)
        assert "SQL Injection - MySQL" in result
        assert "https://example.com/api/users" in result
        assert "POST" in result
        assert "id" in result
        assert "' OR '1'='1" in result
        assert "SQL syntax" in result

    def test_burp_finding_renders_decoded_evidence(
        self, burp_finding: dict[str, Any]
    ) -> None:
        from application.triage.prompts import dast_trace

        result = dast_trace.render(burp_finding, project="demo")
        assert isinstance(result, str)
        assert "Reflected cross-site scripting" in result
        assert "https://example.com/search" in result
        assert "Request:" in result
        assert "Response:" in result

    def test_prompt_includes_inverted_dast_question(
        self, zap_finding: dict[str, Any]
    ) -> None:
        from application.triage.prompts import dast_trace

        result = dast_trace.render(zap_finding, project="demo")
        assert "where" in result.lower()
        assert "vulnerability" in result.lower()
        assert "exploited" in result.lower()

    def test_missing_optional_fields_no_crash(
        self,
    ) -> None:
        from application.triage.prompts import dast_trace

        minimal: dict[str, Any] = {
            "id": 99,
            "tool": "zap",
        }
        result = dast_trace.render(minimal, project="demo")
        assert isinstance(result, str)
        assert "99" in result
