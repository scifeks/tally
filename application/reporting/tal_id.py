"""Finding ID assignment for report-scoped finding identifiers."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.findings.entry import Finding


def resolve_prefix(abbreviation: str, global_prefix: str) -> str:
    """Return the effective finding ID prefix."""
    return (abbreviation or "").strip() or (global_prefix or "").strip()


def _format_id(index: int, width: int, prefix: str) -> str:
    return f"{prefix}-{index:0{width}d}" if prefix else f"{index:0{width}d}"


def assign_tal_ids(
    findings: list[dict[str, Any]],
    prefix: str = "",
) -> list[dict[str, Any]]:
    """Assign zero-padded TAL IDs to each finding."""
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
