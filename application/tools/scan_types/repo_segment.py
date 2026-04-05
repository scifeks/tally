"""RepoSegmentScan — runs a set of tools on every configured repository."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, cast

from application.tools.executor import ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.registry import ToolRegistry
from application.tools.scan_types.execution import (
    dispatch_and_count_ingested,
    execute_tool_passes,
    make_context,
    normalize_success,
)
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.base import ScanType
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig
from domain.tools.scan_types.resources import IExecutionResources

logger = logging.getLogger(__name__)


class RepoSegmentScan(ScanType):
    """Run a set of tools on every configured repository."""

    def __init__(self, tool_names: list[str]) -> None:
        self.tool_names = tool_names

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        registry = cast(ToolRegistry, resources.registry)
        factory = cast(ToolWrapperFactory, resources.factory)
        executor = cast(ToolExecutor, resources.executor)

        start = perf_counter()
        repos = config.config_manager.load_repositories(config.project_name)
        if not repos:
            resources.display.print_status(
                "[yellow]No repositories configured — skipping[/yellow]"
            )
            return ScanSummary(
                total_tools_run=0,
                total_tools_skipped=len(self.tool_names),
                total_tools_failed=0,
                results=[],
                duration_seconds=round(perf_counter() - start, 1),
                findings_ingested=0,
                findings_by_tool={},
            )

        all_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        _reg_tools: list[Any] = registry.get_all_tools()
        _lang_specific: set[str] = {
            t.name for t in _reg_tools if t.name in self.tool_names and t.language_gates
        }

        _total_invocations = len(repos) * len(self.tool_names)
        _invocation = 0

        for repo in repos:
            resources.display.print_status(f"[bold]Repository:[/bold] {repo.name}")
            repo_results: list[ToolResult] = []

            for tool_name in self.tool_names:
                _invocation += 1
                if tool_name in _lang_specific:
                    repo_langs = {lang.lower() for lang in (repo.languages or [])}
                    tool_inst: Any = registry.get_tool(tool_name)
                    gates = (
                        [g.lower() for g in tool_inst.language_gates]
                        if tool_inst is not None
                        else []
                    )
                    if not any(lang in gates for lang in repo_langs):
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name,
                                False,
                                True,
                                0,
                                0.0,
                                f"not applicable for {repo.name} languages",
                            )
                        )
                        total_skipped += 1
                        continue

                tool_config = registry.get_tool_config(tool_name)
                if tool_config is None:
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                    )
                    total_skipped += 1
                    continue

                try:
                    tool: Any = factory.create(tool_name, tool_config)
                except Exception as exc:
                    logger.warning("Factory failed for %r: %s", tool_name, exc)
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "factory error")
                    )
                    total_skipped += 1
                    continue

                if tool.requires_base_urls and not repo.base_urls:
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "no base_urls")
                    )
                    total_skipped += 1
                    continue

                if not tool.check_available():
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not installed")
                    )
                    total_skipped += 1
                    continue

                resources.display.print_running(tool_name, repo.name)
                context = make_context(
                    config.config_manager,
                    config.project_name,
                    config.base_path,
                    registry,
                    repo,
                    tool_config,
                )
                _remaining = (_total_invocations - _invocation) + config.remaining_peers
                result = execute_tool_passes(
                    tool,
                    context,
                    config,
                    executor,
                    remaining_tools=_remaining,
                )

                if result is None:
                    resources.display.print_tool_line(
                        ToolDisplayRow(f"{tool_name}/{repo.name}", False, True, 0, 0.0)
                    )
                    total_skipped += 1
                else:
                    result = normalize_success(result, tool)
                    result.repo = repo.name
                    repo_results.append(result)
                    findings = tool.count_findings(result.parsed_data or {})
                    result.finding_count = findings
                    findings_by_tool[result.tool_name] = (
                        findings_by_tool.get(result.tool_name, 0) + findings
                    )
                    if result.success:
                        total_run += 1
                        total_ingested += dispatch_and_count_ingested(
                            resources.event_bus,
                            ToolCompleted(
                                result,
                                repo.name,
                                config.run_id,
                                config.project_name,
                                config.base_path,
                                repo=repo.name,
                            ),
                        )
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                f"{tool_name}/{repo.name}",
                                True,
                                False,
                                findings,
                                result.duration_seconds,
                            )
                        )
                        if tool_name == "noir" and findings == 0:
                            resources.display.print_status(
                                "    [yellow]⚠ noir found 0 endpoints. "
                                "The framework may not be supported by noir.[/yellow]"
                            )
                            resources.display.print_status(
                                "    [dim]ZAP will fall back to spider-only "
                                "mode for this repository.[/dim]"
                            )
                    else:
                        total_failed += 1
                        total_ingested += dispatch_and_count_ingested(
                            resources.event_bus,
                            ToolCompleted(
                                result,
                                repo.name,
                                config.run_id,
                                config.project_name,
                                config.base_path,
                                repo=repo.name,
                            ),
                        )
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                f"{tool_name}/{repo.name}",
                                False,
                                False,
                                0,
                                result.duration_seconds,
                            )
                        )

            all_results.extend(repo_results)

        return ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=round(perf_counter() - start, 1),
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
