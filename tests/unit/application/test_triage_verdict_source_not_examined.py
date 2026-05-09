"""Unit tests for SourceNotExaminedError detection in parse_verdict."""

from __future__ import annotations

import json

import pytest

from application.triage.verdict import (
    SourceNotExaminedError,
    parse_verdict,
)


def _source_not_examined_obj(**overrides: object) -> dict:
    """Build a source_not_examined error object."""
    base: dict = {
        "error": "source_not_examined",
        "finding_id": 42,
        "reason": "Read tool not available",
    }
    base.update(overrides)
    return base


def _source_not_examined_json(**overrides: object) -> str:
    """Convert a source_not_examined object to JSON."""
    return json.dumps(_source_not_examined_obj(**overrides))


class TestParseVerdictSourceNotExamined:
    def test_source_not_examined_error_raised(self) -> None:
        text = _source_not_examined_json()
        with pytest.raises(SourceNotExaminedError) as exc_info:
            parse_verdict(text, expected_finding_id=42)

        exc = exc_info.value
        assert exc.finding_id == 42
        assert exc.reason == "Read tool not available"

    def test_source_not_examined_preserves_raw_output(self) -> None:
        raw_text = _source_not_examined_json()
        with pytest.raises(SourceNotExaminedError) as exc_info:
            parse_verdict(raw_text, expected_finding_id=42)

        exc = exc_info.value
        assert exc.raw_output == raw_text

    def test_source_not_examined_missing_finding_id_defaults_to_minus_one(
        self,
    ) -> None:
        text = _source_not_examined_json(finding_id=None)
        text_obj = json.loads(text)
        del text_obj["finding_id"]
        text = json.dumps(text_obj)

        with pytest.raises(SourceNotExaminedError) as exc_info:
            parse_verdict(text, expected_finding_id=42)

        exc = exc_info.value
        assert exc.finding_id == -1

    def test_source_not_examined_missing_reason_defaults_to_unknown(
        self,
    ) -> None:
        text = _source_not_examined_json(reason=None)
        text_obj = json.loads(text)
        del text_obj["reason"]
        text = json.dumps(text_obj)

        with pytest.raises(SourceNotExaminedError) as exc_info:
            parse_verdict(text, expected_finding_id=42)

        exc = exc_info.value
        assert exc.reason == "unknown"

    def test_other_error_field_does_not_trigger_source_not_examined(
        self,
    ) -> None:
        text = json.dumps(
            {
                "error": "something_else",
                "finding_id": 42,
                "confidence": "confirmed",
                "finding_type": "vulnerability",
                "severity": "high",
                "reasoning": "User input reaches the sink.",
                "remediation": "Use parameterized queries.",
                "attack_vector": "POST /login password",
            }
        )

        verdict = parse_verdict(text, expected_finding_id=42)
        assert verdict.finding_id == 42
        assert verdict.confidence == "confirmed"

    def test_error_field_with_code_fence(self) -> None:
        text = f"```json\n{_source_not_examined_json()}\n```"
        with pytest.raises(SourceNotExaminedError) as exc_info:
            parse_verdict(text, expected_finding_id=42)

        exc = exc_info.value
        assert exc.finding_id == 42
        assert exc.reason == "Read tool not available"

    def test_error_field_with_prose_before_json(self) -> None:
        text = "The source code could not be retrieved:\n" + _source_not_examined_json()
        with pytest.raises(SourceNotExaminedError) as exc_info:
            parse_verdict(text, expected_finding_id=42)

        exc = exc_info.value
        assert exc.finding_id == 42
