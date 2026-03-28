"""ToolOnRepoScan — runs a single tool against one named repository."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, cast

from application.tools.executor import ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.registry import ToolRegistry
from application.tools.scan_types._helpers import (
    _dispatch_and_count_ingested,
    _execute_tool_passes,
    _make_context,
    _normalize_success,
)
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.base import ScanType
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig
from domain.tools.scan_types.resources import IExecutionResources

logger = logging.getLogger(__name__)


class ToolOnRepoScan(ScanType):
    """Run a single tool against one named repository."""

    def __init__(self, tool_name: str, repo_name: str) -> None:
        self.tool_name = tool_name
        self.repo_name = repo_name

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        registry = cast(ToolRegistry, resources.registry)
        factory = cast(ToolWrapperFactory, resources.factory)
        executor = cast(ToolExecutor, resources.executor)

        repos = config.config_manager.load_repositories(config.project_name)
        repo = next(
            (r for r in repos if r.name.lower() == self.repo_name.lower()), None
        )
        if repo is None:
            raise ValueError(
                f"Repository '{self.repo_name}' not found in"
                f" project '{config.project_name}'"
            )

        tool_config = registry.get_tool_config(self.tool_name)
        if tool_config is None:
            raise ValueError(f"Tool '{self.tool_name}' is not registered.")

        try:
            tool: Any = factory.create(self.tool_name, tool_config)
        except Exception as exc:
            raise ValueError(f"Tool '{self.tool_name}' factory error: {exc}") from exc

        if not tool.check_available():
            raise ValueError(f"Tool '{self.tool_name}' is not installed.")

        config.display.print_scan_header(
            f"Repo Tool Scan: {repo.name} — {self.tool_name}"
        )

        start = perf_counter()
        context = _make_context(
            config.config_manager,
            config.project_name,
            config.base_path,
            registry,
            repo,
            tool_config,
        )
        result = _execute_tool_passes(
            tool,
            context,
            config,
            executor,
            remaining_tools=config.remaining_peers,
        )

        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        if result is None:
            config.display.print_tool_line(
                ToolDisplayRow(self.tool_name, False, True, 0, 0.0)
            )
            total_skipped += 1
        else:
            result = _normalize_success(result, tool)
            results.append(result)
            findings = tool.count_findings(result.parsed_data or {})
            findings_by_tool = {result.tool_name: findings}
            if result.success:
                total_run += 1
                config.display.print_tool_line(
                    ToolDisplayRow(
                        self.tool_name,
                        True,
                        False,
                        findings,
                        result.duration_seconds,
                    )
                )
            else:
                total_failed += 1
                config.display.print_tool_line(
                    ToolDisplayRow(
                        self.tool_name, False, False, 0, result.duration_seconds
                    )
                )

        duration = round(perf_counter() - start, 1)
        for r in results:
            total_ingested += _dispatch_and_count_ingested(
                config.event_bus,
                ToolCompleted(
                    r,
                    repo.name,
                    config.run_id,
                    config.project_name,
                    config.base_path,
                    repo=repo.name,
                ),
            )
        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=findings_by_tool.get(r.tool_name, 0),
                duration_seconds=r.duration_seconds,
            )
            for r in results
        ]
        config.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
        config.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary
