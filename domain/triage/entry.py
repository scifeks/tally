"""Domain entries for the triage surface.

``TriageBatchRow`` and ``TriageRunSummary`` are the row-shaped value
objects returned by ``TriageBatchRepositoryPort`` read methods. They
live in ``domain/`` so port signatures depend on domain types rather
than infrastructure dataclasses (Rule 7). Both are frozen and
field-equivalent to the rows persisted in ``triage_batches`` (with
``TriageRunSummary`` derived from those rows by aggregation).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageBatchRow:
    id: int
    run_id: int
    finding_ids: list[int]
    batch_data: list[dict]
    status: str
    run_attempts: int
    created_at: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class TriageRunSummary:
    """Aggregate view of a triage run derived from triage_batches rows."""

    scan_run_id: int
    status: str
    started_at: str | None
    finished_at: str | None
    total_findings: int
    processed_findings: int
    total_batches: int
    counts_by_status: dict[str, int]
