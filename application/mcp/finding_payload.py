"""Validator for MCP-submitted finding payloads (TAL-148)."""

from __future__ import annotations

import re
from typing import Any

from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
)
from domain.tools.scan_types.models import SEGMENT_ORDER

_CWE_PATTERN = re.compile(r"^CWE-\d+$")


class FindingPayloadError(Exception):
    """Raised when a submitted finding fails schema validation."""


_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "file",
        "file_path",
        "line_number",
        "line_start",
        "description",
        "severity",
        "confidence",
        "cwe",
        "finding_type",
        "rule_id",
        "meta",
        "segment",
        "line_end",
        "reasoning",
        "remediation",
        "attack_vector",
        "code_snippet",
    }
)


def validate_finding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a payload and return a canonicalized dict.

    ``file_path`` and ``line_start`` are aliases for ``file`` and
    ``line_number`` respectively; the returned dict uses the canonical
    names. Unknown top-level keys are rejected; unknown ``meta`` keys
    pass through. Raises :class:`FindingPayloadError` on any failure.
    """
    unknown = set(payload.keys()) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise FindingPayloadError(f"Unknown top-level key: {sorted(unknown)[0]}")

    file_val = payload.get("file") or payload.get("file_path")
    if not file_val:
        raise FindingPayloadError("Missing required field: file (or file_path)")
    if not isinstance(file_val, str):
        raise FindingPayloadError("file must be a string")

    line_val = payload.get("line_number")
    if line_val is None:
        line_val = payload.get("line_start")
    if line_val is None:
        raise FindingPayloadError("Missing required field: line_number (or line_start)")
    if not isinstance(line_val, int):
        raise FindingPayloadError("line_number must be an integer")

    description = payload.get("description", "")
    if not description or not isinstance(description, str):
        raise FindingPayloadError("Missing or invalid required field: description")

    severity = payload.get("severity", "")
    if not severity or not isinstance(severity, str):
        raise FindingPayloadError("Missing or invalid required field: severity")
    if severity not in SEVERITY_LEVELS:
        raise FindingPayloadError(
            f"Invalid severity: {severity} not in {sorted(SEVERITY_LEVELS)}"
        )

    confidence = payload.get("confidence", "")
    if not confidence or not isinstance(confidence, str):
        raise FindingPayloadError("Missing or invalid required field: confidence")
    if confidence not in CONFIDENCE_LEVELS:
        raise FindingPayloadError(
            f"Invalid confidence: {confidence} not in {sorted(CONFIDENCE_LEVELS)}"
        )

    cwe = payload.get("cwe")
    if cwe is None:
        raise FindingPayloadError("Missing required field: cwe")
    if not isinstance(cwe, list) or len(cwe) == 0:
        raise FindingPayloadError("cwe must be a non-empty list")
    for cwe_item in cwe:
        if not isinstance(cwe_item, str) or not _CWE_PATTERN.match(cwe_item):
            raise FindingPayloadError(
                f"Invalid cwe entry: {cwe_item!r} (expected format CWE-N)"
            )

    finding_type = payload.get("finding_type")
    if finding_type is None:
        raise FindingPayloadError("Missing required field: finding_type")
    if not isinstance(finding_type, list) or len(finding_type) == 0:
        raise FindingPayloadError("finding_type must be a non-empty list")
    for ft_item in finding_type:
        if ft_item not in FINDING_TYPES:
            raise FindingPayloadError(
                f"Invalid finding_type: {ft_item!r} not in {sorted(FINDING_TYPES)}"
            )

    rule_id = payload.get("rule_id", "")
    if not rule_id or not isinstance(rule_id, str):
        raise FindingPayloadError("Missing or invalid required field: rule_id")

    meta = payload.get("meta")
    if meta is None:
        raise FindingPayloadError("Missing required field: meta")
    if not isinstance(meta, dict):
        raise FindingPayloadError("meta must be a dict")

    meta_title = meta.get("title", "")
    if not meta_title or not isinstance(meta_title, str):
        raise FindingPayloadError("Missing or invalid required field in meta: title")

    meta_owasp = meta.get("owasp_name", "")
    if not meta_owasp or not isinstance(meta_owasp, str):
        raise FindingPayloadError(
            "Missing or invalid required field in meta: owasp_name"
        )

    meta_remediation = meta.get("remediation", "")
    if not meta_remediation or not isinstance(meta_remediation, str):
        raise FindingPayloadError(
            "Missing or invalid required field in meta: remediation"
        )

    segment = payload.get("segment")
    if segment is not None:
        if not isinstance(segment, str):
            raise FindingPayloadError("segment must be a string")
        if segment not in SEGMENT_ORDER:
            raise FindingPayloadError(
                f"Invalid segment: {segment} not in {SEGMENT_ORDER}"
            )

    line_end = payload.get("line_end")
    if line_end is not None and not isinstance(line_end, int):
        raise FindingPayloadError("line_end must be an integer")

    for opt_field in ("reasoning", "remediation", "attack_vector", "code_snippet"):
        val = payload.get(opt_field)
        if val is not None and not isinstance(val, str):
            raise FindingPayloadError(f"{opt_field} must be a string")

    result: dict[str, Any] = {
        "file": file_val,
        "line_number": line_val,
        "description": description,
        "severity": severity,
        "confidence": confidence,
        "cwe": cwe,
        "finding_type": finding_type,
        "rule_id": rule_id,
        "meta": meta,
    }

    if segment is not None:
        result["segment"] = segment
    if line_end is not None:
        result["line_end"] = line_end
    for opt_field in ("reasoning", "remediation", "attack_vector", "code_snippet"):
        if opt_field in payload:
            result[opt_field] = payload[opt_field]

    return result
