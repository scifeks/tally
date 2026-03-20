"""FullScan — runs all segments across all repos in SEGMENT_ORDER."""

from __future__ import annotations

from time import perf_counter

from core.tools.base import ToolResult
from core.tools.display import ToolDisplayRow
from core.tools.scan_types._helpers import _tools_for_segment
from core.tools.scan_types.base import ExecutionResources, ScanType
from core.tools.scan_types.models import SEGMENT_ORDER, ScanSummary, ScanTypeConfig
from core.tools.scan_types.network_segment import NetworkSegmentScan
from core.tools.scan_types.repo_segment import RepoSegmentScan


class FullScan(ScanType):
    """Run all segments across all repos in SEGMENT_ORDER."""

    def __init__(self, exclude_segments: list[str] | None = None) -> None:
        self.exclude_segments = exclude_segments or []

    def execute(
        self, config: ScanTypeConfig, resources: ExecutionResources
    ) -> ScanSummary:
        start = perf_counter()

        all_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        merged_fbt: dict[str, int] = {}

        config.display.print_scan_header(f"Full Scan: {config.project_name}")

        for segment in SEGMENT_ORDER:
            if segment in self.exclude_segments:
                config.display.print_status(f"[dim]Skipping segment: {segment}[/dim]")
                continue

            config.display.print_segment_header(segment)

            if segment == "network":
                seg_summary = NetworkSegmentScan().execute(config, resources)
            else:
                seg_summary = RepoSegmentScan(
                    _tools_for_segment(segment, resources.registry)
                ).execute(config, resources)

            all_results.extend(seg_summary.results)
            total_run += seg_summary.total_tools_run
            total_skipped += seg_summary.total_tools_skipped
            total_failed += seg_summary.total_tools_failed
            total_ingested += seg_summary.findings_ingested
            for tool_name, count in seg_summary.findings_by_tool.items():
                merged_fbt[tool_name] = merged_fbt.get(tool_name, 0) + count

        duration = round(perf_counter() - start, 1)
        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=merged_fbt.get(r.tool_name, 0),
                duration_seconds=r.duration_seconds,
            )
            for r in all_results
        ]
        config.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=merged_fbt,
        )
        config.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary
