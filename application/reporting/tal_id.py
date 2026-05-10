"""Finding ID assignment for report-scoped finding identifiers."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.findings.entry import Finding


def resolve_prefix(abbreviation: str, global_prefix: str) -> str:
    """Resolve the effective finding ID prefix.

    Priority:
    1. Project-level abbreviation (if set and non-empty).
    2. Global ``report_finding_prefix`` (if set and non-empty).
    3. Empty string: callers fall back to numeric-only IDs (e.g. ``001``).
    """
    return (abbreviation or "").strip() or (global_prefix or "").strip()


def _format_id(index: int, width: int, prefix: str) -> str:
    return f"{prefix}-{index:0{width}d}" if prefix else f"{index:0{width}d}"


def assign_tal_ids(
    findings: list[dict],  # type: ignore[type-arg]
    prefix: str = "",
) -> list[dict]:  # type: ignore[type-arg]
    """Return new dicts with ``tal_id`` populated.

    The caller filters to ``should_report=1`` and sorts before calling.
    IDs zero-pad to a minimum of 3 digits, expanding when the count exceeds
    999 so all IDs share the same width.
    """
    if not findings:
        return []
    width = max(3, len(str(len(findings))))
    return [
        {**finding, "tal_id": _format_id(i, width, prefix)}
        for i, finding in enumerate(findings, start=1)
    ]


def assign_tal_ids_to_findings(
    findings: list[Finding],
    prefix: str = "",
) -> list[Finding]:
    """Return new ``Finding`` instances with ``tal_id`` populated."""
    if not findings:
        return []
    width = max(3, len(str(len(findings))))
    return [
        replace(finding, tal_id=_format_id(i, width, prefix))
        for i, finding in enumerate(findings, start=1)
    ]
