"""NetworkSegmentScan — runs nmap for all configured profiles."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from application.tools.scan_types._helpers import _execute_tool_passes, _make_context
from application.tools.scan_types.resources import ExecutionResources
from core.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.base import ScanType
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig

logger = logging.getLogger(__name__)


class NetworkSegmentScan(ScanType):
    """Run nmap for all configured profiles as a single merged result."""

    def execute(
        self, config: ScanTypeConfig, resources: ExecutionResources
    ) -> ScanSummary:
        start = perf_counter()
        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        nmap_cfg = config.config_manager.load_nmap_hosts(config.project_name)
        profiles = nmap_cfg.profiles if nmap_cfg else {}
        if not profiles:
            config.display.print_status(
                "[yellow]No nmap profiles configured"
                " — skipping network segment[/yellow]"
            )
            total_skipped += 1
            return ScanSummary(
                total_tools_run=total_run,
                total_tools_skipped=total_skipped,
                total_tools_failed=total_failed,
                results=results,
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=total_ingested,
                findings_by_tool=findings_by_tool,
            )

        tool_config = resources.registry.get_tool_config("nmap")
        if tool_config is None:
            config.display.print_tool_line(
                ToolDisplayRow("nmap", False, True, 0, 0.0, "not registered")
            )
            total_skipped += 1
            return ScanSummary(
                total_tools_run=total_run,
                total_tools_skipped=total_skipped,
                total_tools_failed=total_failed,
                results=results,
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=total_ingested,
                findings_by_tool=findings_by_tool,
            )

        try:
            tool: Any = resources.factory.create("nmap", tool_config)
        except Exception as exc:
            logger.warning("Factory failed for 'nmap': %s", exc)
            config.display.print_tool_line(
                ToolDisplayRow("nmap", False, True, 0, 0.0, "factory error")
            )
            total_skipped += 1
            return ScanSummary(
                total_tools_run=total_run,
                total_tools_skipped=total_skipped,
                total_tools_failed=total_failed,
                results=results,
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=total_ingested,
                findings_by_tool=findings_by_tool,
            )

        if not tool.check_available():
            config.display.print_tool_line(
                ToolDisplayRow("nmap", False, True, 0, 0.0, "not installed")
            )
            total_skipped += 1
            return ScanSummary(
                total_tools_run=total_run,
                total_tools_skipped=total_skipped,
                total_tools_failed=total_failed,
                results=results,
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=total_ingested,
                findings_by_tool=findings_by_tool,
            )

        config.display.print_running("nmap")
        context = _make_context(
            config.config_manager,
            config.project_name,
            config.base_path,
            resources.registry,
            None,
            tool_config,
        )
        result = _execute_tool_passes(tool, context, config, resources.executor)

        if result is None:
            config.display.print_tool_line(ToolDisplayRow("nmap", False, True, 0, 0.0))
            total_skipped += 1
        else:
            results.append(result)
            findings = tool.count_findings(result.parsed_data or {})
            findings_by_tool["nmap"] = findings_by_tool.get("nmap", 0) + findings
            if result.success:
                total_run += 1
                config.display.print_tool_line(
                    ToolDisplayRow(
                        "nmap", True, False, findings, result.duration_seconds
                    )
                )
                config.event_bus.dispatch(
                    ToolCompleted(
                        result,
                        config.project_name,
                        config.run_id,
                        config.project_name,
                        config.base_path,
                    )
                )
            else:
                total_failed += 1
                config.display.print_tool_line(
                    ToolDisplayRow("nmap", False, False, 0, result.duration_seconds)
                )

        return ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results,
            duration_seconds=round(perf_counter() - start, 1),
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
