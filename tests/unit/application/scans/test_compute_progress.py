"""Tests for ScansService.compute_progress."""

from __future__ import annotations

from application.scans.scans_service import ScansService
from domain.scans.entry import ScanRunRow, ToolRunRow


def _scan(status: str) -> ScanRunRow:
    return ScanRunRow(
        id=1,
        project_id=1,
        args={},
        created_at=None,
        status=status,
        started_at=None,
        finished_at=None,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
        findings_count=None,
    )


def _tool(status: str, reason: str | None = None) -> ToolRunRow:
    return ToolRunRow(
        id=1,
        run_id=1,
        tool="semgrep",
        findings_count=0,
        repo_id=1,
        repo_name="shop",
        service="api",
        domain="code",
        status=status,
        started_at=None,
        finished_at=None,
        exit_code=None,
        reason=reason,
        enriched_count=None,
        total_to_enrich=None,
    )


class TestComputeProgress:
    def test_failed_row_with_a_reason_counts_as_failed(self) -> None:
        progress = ScansService.compute_progress(
            _scan("running"),
            [_tool("failed", "not installed"), _tool("skipped", "declined")],
        )
        assert (progress.counts.failed, progress.counts.skipped) == (1, 1)

    def test_percent_is_finished_rows_over_rows_so_far(self) -> None:
        progress = ScansService.compute_progress(
            _scan("running"), [_tool("done"), _tool("running")]
        )
        assert progress.progress == 50
        assert progress.counts.queued == 0
