"""Unit tests for the DAST prompt renderer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from application.triage.prompts.output_instructions import STDOUT_OUTPUT_INSTRUCTION

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

        result = dast_trace.render(
            zap_finding, project="demo", output_instruction=STDOUT_OUTPUT_INSTRUCTION
        )
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

        result = dast_trace.render(
            burp_finding, project="demo", output_instruction=STDOUT_OUTPUT_INSTRUCTION
        )
        assert isinstance(result, str)
        assert "Reflected cross-site scripting" in result
        assert "https://example.com/search" in result
        assert "Request:" in result
        assert "Response:" in result

    def test_prompt_includes_inverted_dast_question(
        self, zap_finding: dict[str, Any]
    ) -> None:
        from application.triage.prompts import dast_trace

        result = dast_trace.render(
            zap_finding, project="demo", output_instruction=STDOUT_OUTPUT_INSTRUCTION
        )
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
        result = dast_trace.render(
            minimal, project="demo", output_instruction=STDOUT_OUTPUT_INSTRUCTION
        )
        assert isinstance(result, str)
        assert "99" in result


class TestOutputInstruction:
    def test_render_includes_output_instruction_verbatim(self) -> None:
        from application.triage.prompts import dast_trace

        out = dast_trace.render(
            {"id": 42, "tool": "zap"},
            project="demo",
            output_instruction="SENTINEL_INSTRUCTION_123",
        )
        assert "SENTINEL_INSTRUCTION_123" in out

    def test_render_omits_default_file_path_when_caller_overrides(self) -> None:
        from application.triage.prompts import dast_trace

        out = dast_trace.render(
            {"id": 42, "tool": "zap"},
            project="demo",
            output_instruction="emit JSON to stdout",
        )
        assert "/workspace/out/verdict.json" not in out

    def test_render_requires_output_instruction(self) -> None:
        from application.triage.prompts import dast_trace

        kwargs: dict[str, Any] = {"project": "demo"}
        with pytest.raises(TypeError):
            dast_trace.render({"id": 42, "tool": "zap"}, **kwargs)
