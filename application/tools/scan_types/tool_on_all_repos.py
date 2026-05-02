"""ToolOnAllReposScan: runs a single tool against all configured repositories."""

from __future__ import annotations

from time import perf_counter

from application.tools.scan_types.base import ScanType
from application.tools.scan_types.models import ScanTypeConfig
from application.tools.scan_types.repo_segment import RepoSegmentScan
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.models import ScanSummary
from domain.tools.scan_types.resources import IExecutionResources


class ToolOnAllReposScan(ScanType):
    """Run a single tool against all configured repositories."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        start = perf_counter()

        resources.display.print_scan_header(
            f"Repo Tool Scan: {config.project_name} — {self.tool_name}"
        )

        tool_inst = resources.registry.get_tool(self.tool_name)
        seg_name = tool_inst.scan_segment if tool_inst is not None else ""
        seg_summary = RepoSegmentScan([self.tool_name], segment_name=seg_name).execute(
            config, resources
        )

        duration = round(perf_counter() - start, 1)
        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=r.finding_count,
                duration_seconds=r.duration_seconds,
                repo=r.repo,
            )
            for r in seg_summary.results
        ]
        resources.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=seg_summary.total_tools_run,
            total_tools_skipped=seg_summary.total_tools_skipped,
            total_tools_failed=seg_summary.total_tools_failed,
            results=seg_summary.results,
            duration_seconds=duration,
            findings_ingested=seg_summary.findings_ingested,
            findings_by_tool=seg_summary.findings_by_tool,
        )
        resources.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary
