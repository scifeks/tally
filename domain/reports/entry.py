"""Domain entries for the reports surface.

``ReportRow`` and ``DraftRow`` are the row-shaped value objects returned
by ``ReportRepositoryPort`` and ``DraftRepositoryPort``. They live in
``domain/`` so port signatures depend on domain types rather than
infrastructure dataclasses (Rule 7). Both are frozen and field-equivalent
to the rows persisted in ``reports`` and ``drafts``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportRow:
    id: int
    project_id: int | None
    scan_run_id: int | None
    format: str
    filename: str
    filepath: str
    status: str
    retention_tier: str
    file_size_bytes: int | None
    error: str | None
    created_at: str | None
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class DraftRow:
    section: str
    status: str
    original_filename: str | None
    generated_at: str | None
    reviewed_at: str | None
