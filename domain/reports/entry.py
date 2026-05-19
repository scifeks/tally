"""Row dataclasses for the reports and drafts tables."""

from __future__ import annotations

from dataclasses import dataclass

REPORT_STATUSES = (
    "queued",
    "running",
    "done",
    "failed",
    "cancelling",
    "cancelled",
)


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
    display_name: str | None = None
    notes: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class DraftRow:
    section: str
    status: str
    original_filename: str | None
    generated_at: str | None
    reviewed_at: str | None
    error: str | None = None
