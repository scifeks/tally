"""Verdict dataclass and parser for one-shot triage agent output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
)

_REQUIRED_FIELDS = (
    "finding_id",
    "confidence",
    "finding_type",
    "severity",
    "reasoning",
    "remediation",
    "attack_vector",
    "call_stack",
)


class VerdictParseError(Exception):
    """Agent output cannot be parsed into a valid Verdict."""

    def __init__(
        self,
        problem: str,
        partial: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(problem)
        self.problem = problem
        self.partial = partial


@dataclass(frozen=True)
class Verdict:
    finding_id: int
    confidence: str
    finding_type: str
    severity: str
    reasoning: str
    remediation: str
    attack_vector: str
    call_stack: list[str] = field(default_factory=list)


def parse_verdict(text: str, *, expected_finding_id: int) -> Verdict:
    """Parse agent text output into a Verdict.

    Raises VerdictParseError if the text cannot be parsed or
    validated.
    """
    obj = _extract_json_object(text)
    _validate_fields(obj, expected_finding_id)
    return Verdict(
        finding_id=obj["finding_id"],
        confidence=obj["confidence"],
        finding_type=obj["finding_type"],
        severity=obj["severity"],
        reasoning=obj["reasoning"],
        remediation=obj["remediation"],
        attack_vector=obj["attack_vector"],
        call_stack=[str(e) for e in obj["call_stack"]],
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    s = text.strip()
    if not s:
        raise VerdictParseError("empty verdict text")

    s = _strip_code_fences(s)

    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        first_brace = s.find("{")
        if first_brace == -1:
            raise VerdictParseError("no JSON object found")
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(s, idx=first_brace)
        except json.JSONDecodeError as exc:
            raise VerdictParseError(f"could not parse JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise VerdictParseError(f"verdict is not an object (got {type(obj).__name__})")
    return obj


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

    if not isinstance(obj["call_stack"], list):
        raise VerdictParseError(
            "call_stack is not a list",
            partial=obj,
        )
