"""Domain value objects for findings.

``HistoryRow`` represents a finding history entry from ``FindingHistoryRepositoryPort``.
``Finding`` represents a findings table row with JSON fields parsed
and severity translated from integer rank to lowercase label.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from domain.findings.severity import Severity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoryRow:
    id: int
    finding_id: int
    timestamp: str
    before_values: dict[str, Any]
    after_values: dict[str, Any]
    inference_context: dict[str, Any] | None
    source: str


@dataclass(frozen=True)
class Finding:
    """Parsed row from the ``findings`` table.

    Severity is the lowercase label string (``critical``/``high``/...);
    rank → label translation happens in ``from_row`` via
    ``Severity.from_rank``. JSON columns (``meta``, ``finding_type``,
    ``cwe``) are parsed.
    """

    id: int
    fingerprint: str | None
    run_id: int | None
    tool: str | None
    domain: str | None
    segment: str | None
    finding_type: list[str] = field(default_factory=list)
    severity: str | None = None
    confidence: str | None = None
    file: str | None = None
    rule_id: str | None = None
    url: str | None = None
    vulnerability_id: str | None = None
    package_name: str | None = None
    ecosystem: str | None = None
    description: str | None = None
    package_version: str | None = None
    cwe: list[str] = field(default_factory=list)
    enriched: bool = False
    meta: dict[str, Any] = field(default_factory=dict)
    first_seen: str | None = None
    last_seen: str | None = None
    seen_count: int | None = None
    status: str | None = None
    triaged_at: str | None = None
    triaged_by: str | None = None
    should_report: bool = False
    business_impact: str | None = None
    tal_id: str | None = None
    duplicate_of: int | None = None
    repo_id: int | None = None

    @classmethod
    def from_row(cls, row: Any) -> Finding:
        """Build a Finding from a ``findings``-table row.

        Tolerates malformed JSON in ``meta``/``finding_type``/``cwe``
        and unknown severity ranks by falling back to empty/None values
        rather than raising.
        """
        return cls(
            id=int(row["id"]),
            fingerprint=row["fingerprint"],
            run_id=row["run_id"],
            tool=row["tool"],
            domain=row["domain"],
            segment=row["segment"],
            finding_type=_parse_json_list(row["finding_type"]),
            severity=_severity_label(row["severity"]),
            confidence=row["confidence"],
            file=row["file"],
            rule_id=row["rule_id"],
            url=row["url"],
            vulnerability_id=row["vulnerability_id"],
            package_name=row["package_name"],
            ecosystem=row["ecosystem"],
            description=row["description"],
            package_version=row["package_version"],
            cwe=_parse_json_list(row["cwe"]),
            enriched=bool(row["enriched"]),
            meta=_parse_meta(row["meta"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            seen_count=row["seen_count"],
            status=row["status"],
            triaged_at=row["triaged_at"],
            triaged_by=row["triaged_by"],
            should_report=bool(row["should_report"]),
            business_impact=row["business_impact"],
            tal_id=row["tal_id"],
            duplicate_of=row["duplicate_of"],
            repo_id=row["repo_id"],
        )


def _severity_label(rank: Any) -> str | None:
    if rank is None:
        return None
    try:
        return Severity.from_rank(int(rank)).label
    except (ValueError, TypeError):
        return None


def _parse_json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return []


def _parse_meta(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}
