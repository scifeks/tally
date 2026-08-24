"""Verdict dataclass and parser for one-shot triage agent output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from domain.tools.constants import (
    ACCESS_REQUIRED_LEVELS,
    CONFIDENCE_LEVELS,
    EXPLOITATION_COMPLEXITY_LEVELS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
    USER_INTERACTION_LEVELS,
)

_REQUIRED_FIELDS = (
    "finding_id",
    "confidence",
    "finding_type",
    "severity",
    "reasoning",
    "remediation",
    "attack_vector",
    "access_required",
    "exploitation_complexity",
    "user_interaction",
)


class VerdictParseError(Exception):
    """Agent output cannot be parsed into a valid Verdict."""

    def __init__(
        self,
        problem: str,
        partial: dict[str, Any] | None = None,
        raw_output: str = "",
    ) -> None:
        super().__init__(problem)
        self.problem = problem
        self.partial = partial
        self.raw_output = raw_output


class SourceNotExaminedError(Exception):
    """Agent reported it could not examine the source files."""

    def __init__(
        self,
        finding_id: int,
        reason: str,
        raw_output: str = "",
    ) -> None:
        super().__init__(reason)
        self.finding_id = finding_id
        self.reason = reason
        self.raw_output = raw_output


@dataclass(frozen=True)
class Verdict:
    finding_id: int
    confidence: str
    finding_type: str
    severity: str
    reasoning: str
    remediation: str
    attack_vector: str
    access_required: str
    exploitation_complexity: str
    user_interaction: str
    call_stack: list[str] = field(default_factory=list)


def parse_verdict(text: str, *, expected_finding_id: int) -> Verdict:
    """Parse agent text output into a Verdict.

    Raises VerdictParseError if the text cannot be parsed or
    validated.
    """
    try:
        obj = _extract_json_object(text)
    except VerdictParseError as exc:
        exc.raw_output = text
        raise

    if obj.get("error") == "source_not_examined":
        raise SourceNotExaminedError(
            finding_id=obj.get("finding_id", -1),
            reason=obj.get("reason", "unknown"),
            raw_output=text,
        )

    try:
        _validate_fields(obj, expected_finding_id)
    except VerdictParseError as exc:
        exc.raw_output = text
        raise
    return Verdict(
        finding_id=obj["finding_id"],
        confidence=obj["confidence"],
        finding_type=obj["finding_type"],
        severity=obj["severity"],
        reasoning=obj["reasoning"],
        remediation=obj["remediation"],
        attack_vector=obj["attack_vector"],
        access_required=obj["access_required"],
        exploitation_complexity=obj["exploitation_complexity"],
        user_interaction=obj["user_interaction"],
        call_stack=[str(e) for e in obj.get("call_stack", [])],
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    s = text.strip()
    if not s:
        raise VerdictParseError("empty verdict text")

    s = _strip_code_fences(s)

    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    pos = 0
    while True:
        brace = s.find("{", pos)
        if brace == -1:
            raise VerdictParseError("no JSON object found in text")
        try:
            obj, _ = decoder.raw_decode(s, brace)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        pos = brace + 1


def _strip_code_fences(s: str) -> str:
    if not s.startswith("```"):
        return s
    end = s.rfind("```", 3)
    if end <= 0:
        return s
    inner = s[3:end].strip()
    if inner.startswith("json"):
        inner = inner[4:].strip()
    return inner


def _validate_fields(obj: dict[str, Any], expected_finding_id: int) -> None:
    missing = [f for f in _REQUIRED_FIELDS if f not in obj]
    if missing:
        raise VerdictParseError(f"missing fields: {missing}", partial=obj)

    finding_id = obj["finding_id"]
    if not isinstance(finding_id, int) or isinstance(finding_id, bool):
        raise VerdictParseError(
            f"finding_id must be an integer, got {type(finding_id).__name__}",
            partial=obj,
        )

    if finding_id != expected_finding_id:
        raise VerdictParseError(
            f"finding_id mismatch: got {finding_id!r}, expected {expected_finding_id}",
            partial=obj,
        )

    confidence = obj["confidence"]
    if confidence not in CONFIDENCE_LEVELS:
        raise VerdictParseError(
            f"invalid confidence {confidence!r}; "
            f"expected one of {sorted(CONFIDENCE_LEVELS)}",
            partial=obj,
        )

    finding_type = obj["finding_type"]
    if finding_type not in FINDING_TYPES:
        raise VerdictParseError(
            f"invalid finding_type {finding_type!r}; "
            f"expected one of {sorted(FINDING_TYPES)}",
            partial=obj,
        )

    severity = obj["severity"]
    if severity not in SEVERITY_LEVELS:
        raise VerdictParseError(
            f"invalid severity {severity!r}; expected one of {sorted(SEVERITY_LEVELS)}",
            partial=obj,
        )

    access_required = obj["access_required"]
    if access_required not in ACCESS_REQUIRED_LEVELS:
        raise VerdictParseError(
            f"invalid access_required {access_required!r}; "
            f"expected one of {sorted(ACCESS_REQUIRED_LEVELS)}",
            partial=obj,
        )

    exploitation_complexity = obj["exploitation_complexity"]
    if exploitation_complexity not in EXPLOITATION_COMPLEXITY_LEVELS:
        raise VerdictParseError(
            f"invalid exploitation_complexity "
            f"{exploitation_complexity!r}; expected one of "
            f"{sorted(EXPLOITATION_COMPLEXITY_LEVELS)}",
            partial=obj,
        )

    user_interaction = obj["user_interaction"]
    if user_interaction not in USER_INTERACTION_LEVELS:
        raise VerdictParseError(
            f"invalid user_interaction {user_interaction!r}; "
            f"expected one of {sorted(USER_INTERACTION_LEVELS)}",
            partial=obj,
        )

    cs = obj.get("call_stack")
    if cs is not None and not isinstance(cs, list):
        raise VerdictParseError(
            "call_stack is not a list",
            partial=obj,
        )

    _check_contradictions(obj)


def _check_contradictions(obj: dict[str, Any]) -> None:
    confidence = obj["confidence"]
    severity = obj["severity"]
    finding_type = obj["finding_type"]
    access_required = obj["access_required"]
    complexity = obj["exploitation_complexity"]
    interaction = obj["user_interaction"]

    if confidence == "false_positive" and severity not in (
        "low",
        "informational",
    ):
        raise VerdictParseError(
            f"contradictory: false_positive with severity={severity!r}",
            partial=obj,
        )

    if finding_type == "informational" and severity in (
        "critical",
        "high",
    ):
        raise VerdictParseError(
            f"contradictory: informational finding_type with severity={severity!r}",
            partial=obj,
        )

    if confidence == "confirmed" and severity == "informational":
        raise VerdictParseError(
            "contradictory: confirmed confidence with informational severity",
            partial=obj,
        )

    modifiers = sum(
        [
            access_required == "privileged",
            complexity == "high",
            interaction == "required",
        ]
    )
    if modifiers >= 2 and severity == "critical":
        raise VerdictParseError(
            "contradictory: multiple exploit prerequisites "
            "(privileged access, high complexity, or "
            "user interaction) preclude critical severity",
            partial=obj,
        )

    if finding_type == "weakness" and severity == "critical":
        raise VerdictParseError(
            "contradictory: weakness finding_type with critical severity",
            partial=obj,
        )
