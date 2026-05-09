"""Unit tests for the one-shot triage verdict parser."""

from __future__ import annotations

import json

import pytest

from application.triage.verdict import (
    Verdict,
    VerdictParseError,
    parse_verdict,
)


def _valid_obj(**overrides: object) -> dict:
    base: dict = {
        "finding_id": 42,
        "confidence": "confirmed",
        "finding_type": "vulnerability",
        "severity": "high",
        "reasoning": "User input reaches the sink.",
        "remediation": "Use parameterized queries.",
        "attack_vector": "POST /login password",
        "call_stack": ["app.php:10 handle", "db.php:55 query"],
    }
    base.update(overrides)
    return base


def _valid_json(**overrides: object) -> str:
    return json.dumps(_valid_obj(**overrides))


class TestParseVerdictHappyPath:
    @pytest.mark.parametrize(
        "text_fn",
        [
            pytest.param(lambda: _valid_json(), id="bare_json"),
            pytest.param(
                lambda: f"```json\n{_valid_json()}\n```",
                id="json_code_fence",
            ),
            pytest.param(
                lambda: f"```\n{_valid_json()}\n```",
                id="unmarked_code_fence",
            ),
            pytest.param(
                lambda: _valid_json() + "\n" + json.dumps({"extra": 1}),
                id="multi_json",
            ),
            pytest.param(
                lambda: "Here is my verdict:\n" + _valid_json(),
                id="prose_before_json",
            ),
            pytest.param(
                lambda: _valid_json(call_stack=[]),
                id="empty_call_stack",
            ),
            pytest.param(
                lambda: _valid_json(call_stack=["a.py:1 foo", "b.py:2 bar"]),
                id="non_empty_call_stack",
            ),
        ],
    )
    def test_valid_variations(self, text_fn) -> None:
        verdict = parse_verdict(text_fn(), expected_finding_id=42)
        assert isinstance(verdict, Verdict)
        assert verdict.finding_id == 42
        assert verdict.confidence == "confirmed"
        assert verdict.finding_type == "vulnerability"
        assert verdict.severity == "high"

    def test_call_stack_elements_coerced_to_str(self) -> None:
        text = _valid_json(call_stack=[1, 2.5, True])
        verdict = parse_verdict(text, expected_finding_id=42)
        assert verdict.call_stack == ["1", "2.5", "True"]

    @pytest.mark.parametrize(
        "confidence",
        ["confirmed", "probable", "potential", "false_positive"],
    )
    def test_all_confidence_levels(self, confidence: str) -> None:
        text = _valid_json(confidence=confidence)
        verdict = parse_verdict(text, expected_finding_id=42)
        assert verdict.confidence == confidence

    @pytest.mark.parametrize(
        "finding_type",
        [
            "vulnerability",
            "weakness",
            "misconfiguration",
            "exposure",
            "dependency",
            "informational",
            "secret",
        ],
    )
    def test_all_finding_types(self, finding_type: str) -> None:
        text = _valid_json(finding_type=finding_type)
        verdict = parse_verdict(text, expected_finding_id=42)
        assert verdict.finding_type == finding_type

    @pytest.mark.parametrize(
        "severity",
        ["critical", "high", "medium", "low", "informational"],
    )
    def test_all_severity_levels(self, severity: str) -> None:
        text = _valid_json(severity=severity)
        verdict = parse_verdict(text, expected_finding_id=42)
        assert verdict.severity == severity


class TestParseVerdictFieldValidation:
    @pytest.mark.parametrize(
        "drop_field",
        [
            "finding_id",
            "confidence",
            "finding_type",
            "severity",
            "reasoning",
            "remediation",
            "attack_vector",
        ],
    )
    def test_missing_single_field(self, drop_field: str) -> None:
        obj = _valid_obj()
        del obj[drop_field]
        with pytest.raises(VerdictParseError, match="missing fields"):
            parse_verdict(json.dumps(obj), expected_finding_id=42)

    def test_missing_call_stack_defaults_to_empty(self) -> None:
        obj = _valid_obj()
        del obj["call_stack"]
        v = parse_verdict(json.dumps(obj), expected_finding_id=42)
        assert v.call_stack == []

    def test_missing_multiple_fields(self) -> None:
        obj = _valid_obj()
        del obj["reasoning"]
        del obj["remediation"]
        with pytest.raises(VerdictParseError, match="missing fields"):
            parse_verdict(json.dumps(obj), expected_finding_id=42)

    def test_finding_id_mismatch(self) -> None:
        text = _valid_json(finding_id=99)
        with pytest.raises(VerdictParseError, match="finding_id mismatch"):
            parse_verdict(text, expected_finding_id=42)

    def test_invalid_confidence(self) -> None:
        text = _valid_json(confidence="very_sure")
        with pytest.raises(VerdictParseError, match="invalid confidence"):
            parse_verdict(text, expected_finding_id=42)

    def test_invalid_finding_type(self) -> None:
        text = _valid_json(finding_type="bug")
        with pytest.raises(VerdictParseError, match="invalid finding_type"):
            parse_verdict(text, expected_finding_id=42)

    def test_invalid_severity(self) -> None:
        text = _valid_json(severity="urgent")
        with pytest.raises(VerdictParseError, match="invalid severity"):
            parse_verdict(text, expected_finding_id=42)

    def test_call_stack_not_a_list(self) -> None:
        text = _valid_json(call_stack="app.php:10 handle")
        with pytest.raises(VerdictParseError, match="call_stack is not a list"):
            parse_verdict(text, expected_finding_id=42)

    def test_finding_id_not_integer(self) -> None:
        text = _valid_json(finding_id="42")
        with pytest.raises(VerdictParseError, match="finding_id must be an integer"):
            parse_verdict(text, expected_finding_id=42)

    def test_finding_id_is_bool_rejected(self) -> None:
        text = _valid_json(finding_id=True)
        with pytest.raises(VerdictParseError, match="finding_id must be an integer"):
            parse_verdict(text, expected_finding_id=True)

    def test_parsed_object_not_dict(self) -> None:
        with pytest.raises(VerdictParseError, match="verdict is not an object"):
            parse_verdict("[1, 2, 3]", expected_finding_id=42)

    def test_partial_attached_on_validation_error(self) -> None:
        text = _valid_json(confidence="bad")
        with pytest.raises(VerdictParseError) as exc_info:
            parse_verdict(text, expected_finding_id=42)
        assert exc_info.value.partial is not None
        assert exc_info.value.partial["finding_id"] == 42


class TestParseVerdictParseFailures:
    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("", id="empty_string"),
            pytest.param("   \n\t  ", id="whitespace_only"),
            pytest.param(
                "The finding looks like a false positive.",
                id="plain_prose",
            ),
            pytest.param(
                '{"finding_id": 42, broken}',
                id="malformed_json",
            ),
        ],
    )
    def test_unparseable_input(self, text: str) -> None:
        with pytest.raises(VerdictParseError):
            parse_verdict(text, expected_finding_id=42)

    def test_empty_raises_with_correct_message(self) -> None:
        with pytest.raises(VerdictParseError, match="empty verdict text"):
            parse_verdict("", expected_finding_id=42)

    def test_no_json_raises_with_correct_message(self) -> None:
        with pytest.raises(VerdictParseError, match="no JSON object found"):
            parse_verdict("This is just prose.", expected_finding_id=42)
