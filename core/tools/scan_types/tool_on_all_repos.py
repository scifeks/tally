"""ToolOnAllReposScan — runs a single tool against all configured repositories."""

from __future__ import annotations

from time import perf_counter

from core.tools.display import ToolDisplayRow
from core.tools.scan_types.base import ScanType
from core.tools.scan_types.models import ScanSummary, ScanTypeConfig
from core.tools.scan_types.repo_segment import RepoSegmentScan


class ToolOnAllReposScan(ScanType):
    """Run a single tool against all configured repositories."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
        start = perf_counter()

        config.display.print_scan_header(
            f"Repo Tool Scan: {config.project_name} — {self.tool_name}"
        )

        seg_summary = RepoSegmentScan([self.tool_name]).execute(config)

        duration = round(perf_counter() - start, 1)
        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=seg_summary.findings_by_tool.get(r.tool_name, 0),
                duration_seconds=r.duration_seconds,
            )
            for r in seg_summary.results
        ]
        config.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=seg_summary.total_tools_run,
            total_tools_skipped=seg_summary.total_tools_skipped,
            total_tools_failed=seg_summary.total_tools_failed,
            results=seg_summary.results,
            duration_seconds=duration,
            findings_ingested=seg_summary.findings_ingested,
            findings_by_tool=seg_summary.findings_by_tool,
        )
        config.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary
