"""Domain entries for the scans surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCAN_RUN_STATUSES = (
    "queued",
    "running",
    "done",
    "failed",
    "cancelling",
    "cancelled",
)


@dataclass(frozen=True)
class ScanRunRow:
    id: int
    project_id: int | None
    args: dict[str, Any]
    created_at: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    repo_ids: list[str]
    tool_ids: list[str]
    domains: list[str]
    skip_enrichment: bool
    findings_count: int | None


@dataclass(frozen=True)
class ToolRunRow:
    id: int
    run_id: int
    tool: str | None
    findings_count: int
    repo: str | None
    domain: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    skip_reason: str | None
    enriched_count: int | None
    total_to_enrich: int | None
