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
        "access_required": "none",
        "exploitation_complexity": "low",
        "user_interaction": "none",
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
                lambda: "Analysis: path is `/images/{$id}-{uniqid}`.\n" + _valid_json(),
                id="prose_with_braces_before_json",
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
        overrides = {"confidence": confidence}
        if confidence == "false_positive":
            overrides["severity"] = "low"
        text = _valid_json(**overrides)
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
        overrides = {"finding_type": finding_type}
        if finding_type in ("informational", "weakness"):
            overrides["severity"] = "medium"
        text = _valid_json(**overrides)
        verdict = parse_verdict(text, expected_finding_id=42)
        assert verdict.finding_type == finding_type

    @pytest.mark.parametrize(
        "severity",
        ["critical", "high", "medium", "low", "informational"],
    )
    def test_all_severity_levels(self, severity: str) -> None:
        overrides = {"severity": severity}
        if severity == "informational":
            overrides["confidence"] = "probable"
        text = _valid_json(**overrides)
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
        with pytest.raises(VerdictParseError, match="no JSON object found"):
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


class TestPredicateContradictions:
    @pytest.mark.parametrize(
        "overrides,match",
        [
            pytest.param(
                {
                    "confidence": "false_positive",
                    "severity": "high",
                },
                "contradictory",
                id="fp_high_severity",
            ),
            pytest.param(
                {
                    "confidence": "false_positive",
                    "severity": "critical",
                },
                "contradictory",
                id="fp_critical_severity",
            ),
            pytest.param(
                {
                    "confidence": "false_positive",
                    "severity": "medium",
                },
                "contradictory",
                id="fp_medium_severity",
            ),
            pytest.param(
                {
                    "finding_type": "informational",
                    "severity": "critical",
                    "confidence": "potential",
                },
                "contradictory",
                id="informational_critical",
            ),
            pytest.param(
                {
                    "finding_type": "informational",
                    "severity": "high",
                    "confidence": "potential",
                },
                "contradictory",
                id="informational_high",
            ),
            pytest.param(
                {
                    "confidence": "confirmed",
                    "severity": "informational",
                },
                "contradictory",
                id="confirmed_informational",
            ),
            pytest.param(
                {
                    "access_required": "privileged",
                    "exploitation_complexity": "high",
                    "severity": "critical",
                },
                "contradictory",
                id="privileged_complex_critical",
            ),
            pytest.param(
                {
                    "access_required": "privileged",
                    "user_interaction": "required",
                    "severity": "critical",
                },
                "contradictory",
                id="privileged_interaction_critical",
            ),
            pytest.param(
                {
                    "exploitation_complexity": "high",
                    "user_interaction": "required",
                    "severity": "critical",
                },
                "contradictory",
                id="complex_interaction_critical",
            ),
            pytest.param(
                {
                    "finding_type": "weakness",
                    "severity": "critical",
                    "confidence": "potential",
                },
                "contradictory",
                id="weakness_critical",
            ),
        ],
    )
    def test_contradiction_rejected(self, overrides: dict, match: str) -> None:
        text = _valid_json(**overrides)
        with pytest.raises(VerdictParseError, match=match):
            parse_verdict(text, expected_finding_id=42)

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param(
                {
                    "confidence": "false_positive",
                    "severity": "informational",
                    "finding_type": "informational",
                },
                id="fp_informational_ok",
            ),
            pytest.param(
                {
                    "confidence": "false_positive",
                    "severity": "low",
                    "finding_type": "informational",
                },
                id="fp_low_ok",
            ),
            pytest.param(
                {
                    "access_required": "privileged",
                    "exploitation_complexity": "low",
                    "severity": "critical",
                },
                id="privileged_but_easy_critical_ok",
            ),
            pytest.param(
                {
                    "access_required": "none",
                    "exploitation_complexity": "high",
                    "severity": "critical",
                },
                id="complex_but_unauthd_critical_ok",
            ),
            pytest.param(
                {
                    "finding_type": "weakness",
                    "severity": "high",
                    "confidence": "probable",
                },
                id="weakness_high_ok",
            ),
        ],
    )
    def test_valid_predicate_combinations(self, overrides: dict) -> None:
        text = _valid_json(**overrides)
        verdict = parse_verdict(text, expected_finding_id=42)
        assert isinstance(verdict, Verdict)


class TestNewPredicateFieldValidation:
    def test_invalid_access_required(self) -> None:
        text = _valid_json(access_required="admin")
        with pytest.raises(
            VerdictParseError,
            match="invalid access_required",
        ):
            parse_verdict(text, expected_finding_id=42)

    def test_invalid_exploitation_complexity(self) -> None:
        text = _valid_json(exploitation_complexity="medium")
        with pytest.raises(
            VerdictParseError,
            match="invalid exploitation_complexity",
        ):
            parse_verdict(text, expected_finding_id=42)

    def test_invalid_user_interaction(self) -> None:
        text = _valid_json(user_interaction="optional")
        with pytest.raises(
            VerdictParseError,
            match="invalid user_interaction",
        ):
            parse_verdict(text, expected_finding_id=42)

    @pytest.mark.parametrize("ar", ["none", "authenticated", "privileged"])
    def test_all_access_required_levels(self, ar: str) -> None:
        text = _valid_json(access_required=ar)
        v = parse_verdict(text, expected_finding_id=42)
        assert v.access_required == ar

    @pytest.mark.parametrize("ec", ["low", "high"])
    def test_all_exploitation_complexity_levels(self, ec: str) -> None:
        text = _valid_json(exploitation_complexity=ec)
        v = parse_verdict(text, expected_finding_id=42)
        assert v.exploitation_complexity == ec

    @pytest.mark.parametrize("ui", ["none", "required"])
    def test_all_user_interaction_levels(self, ui: str) -> None:
        text = _valid_json(user_interaction=ui)
        v = parse_verdict(text, expected_finding_id=42)
        assert v.user_interaction == ui
