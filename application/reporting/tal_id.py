"""Finding ID assignment for report-scoped finding identifiers."""

from __future__ import annotations

_SEVERITY_ORDER: tuple[str, ...] = (
    "critical",
    "high",
    "medium",
    "low",
    "informational",
)


def resolve_prefix(abbreviation: str, global_prefix: str) -> str:
    """Resolve the effective finding ID prefix.

    Priority:
    1. Project-level abbreviation (if set and non-empty).
    2. Global ``report_finding_prefix`` (if set and non-empty).
    3. Empty string — callers fall back to numeric-only IDs (e.g. ``001``).

    Args:
        abbreviation:   Project-level abbreviation from ``ProjectConfig``.
        global_prefix:  ``report_finding_prefix`` from ``GlobalConfig``.

    Returns:
        The resolved prefix string, or ``""`` if both inputs are empty.
    """
    return (abbreviation or "").strip() or (global_prefix or "").strip()


def assign_tal_ids(
    findings: list[dict],  # type: ignore[type-arg]
    prefix: str = "",
) -> list[dict]:  # type: ignore[type-arg]
    """Assign finding IDs to a pre-filtered, pre-sorted list of findings.

    The caller is responsible for filtering to ``should_report=1`` and sorting
    by severity (critical → informational) then ``first_seen`` ascending before
    calling this function.

    IDs are zero-padded to a minimum of 3 digits.  When the finding count
    exceeds 999 the padding width auto-expands so all IDs share the same
    width (e.g. 1 000 findings → 4 digits).

    When *prefix* is provided the format is ``PREFIX-001``, ``PREFIX-002``, …
    When *prefix* is empty the format is ``001``, ``002``, … (numeric only).

    Args:
        findings: List of finding dicts (not mutated).
        prefix:   Finding ID prefix resolved via :func:`resolve_prefix`.

    Returns:
        New list of dicts with ``tal_id`` populated.
    """
    if not findings:
        return []

    width = max(3, len(str(len(findings))))
    result: list[dict] = []  # type: ignore[type-arg]
    for i, finding in enumerate(findings, start=1):
        fid = f"{prefix}-{i:0{width}d}" if prefix else f"{i:0{width}d}"
        result.append({**finding, "tal_id": fid})
    return result
