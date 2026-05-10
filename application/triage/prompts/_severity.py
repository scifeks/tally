"""Severity rank-to-label conversion for triage prompts."""

from __future__ import annotations

from typing import Any

from domain.findings.severity import Severity


def format_severity(raw: Any) -> str:
    """Convert a severity value to its human-readable label.

    Handles integer ranks from the DB, string labels, and None.
    """
    if raw is None:
        return "n/a"
    if isinstance(raw, int):
        try:
            return Severity.from_rank(raw).label
        except ValueError:
            return str(raw)
    return str(raw)
