"""TAL-ID assignment for report-scoped finding identifiers."""

from __future__ import annotations

_SEVERITY_ORDER: tuple[str, ...] = (
    "critical",
    "high",
    "medium",
    "low",
    "informational",
)


def assign_tal_ids(findings: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    """Assign TAL-IDs to a pre-filtered, pre-sorted list of findings.

    The caller is responsible for filtering to ``should_report=1`` and sorting
    by severity (critical → informational) then ``first_seen`` ascending before
    calling this function.

    IDs are zero-padded to a minimum of 3 digits.  When the finding count
    exceeds 999 the padding width auto-expands so all IDs share the same
    width (e.g. 1 000 findings → TAL-1000 … TAL-1000, 4 digits).

    Args:
        findings: List of finding dicts (not mutated).

    Returns:
        New list of dicts with ``tal_id`` populated.
    """
    if not findings:
        return []

    width = max(3, len(str(len(findings))))
    result: list[dict] = []  # type: ignore[type-arg]
    for i, finding in enumerate(findings, start=1):
        result.append({**finding, "tal_id": f"TAL-{i:0{width}d}"})
    return result
