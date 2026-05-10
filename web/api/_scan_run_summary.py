"""Shared mapper from a ScanRunRow domain row to the wire ScanRunSummary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from web.api.schemas import ScanRunSummary

if TYPE_CHECKING:
    from domain.scans.entry import ScanRunRow


def scan_run_to_summary(row: ScanRunRow) -> ScanRunSummary:
    """Translate a ScanRunRow into the public ScanRunSummary response model."""
    return ScanRunSummary(
        id=row.id,
        project_id=row.project_id,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        repo_ids=row.repo_ids,
        tool_ids=row.tool_ids,
        domains=row.domains,
        findings_count=row.findings_count,
        skip_enrichment=row.skip_enrichment,
    )
