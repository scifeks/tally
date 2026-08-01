"""RepoScan: runs all applicable tools for a single repo."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, cast

from application.tools.executor import ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.registry import ToolRegistry
from application.tools.scan_types.base import ScanType
from application.tools.scan_types.execution import (
    dispatch_and_count_ingested,
    execute_tool_passes,
    make_context,
    normalize_success,
    ordered_repo_tools,
    should_skip_sca_tool,
)
from application.tools.scan_types.models import ScanTypeConfig
from core.detection.noir import noir_skip_reason
from domain.pipeline import scan_events as se
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.models import ScanSummary
from domain.tools.scan_types.resources import IExecutionResources

logger = logging.getLogger(__name__)


def _emit_skipped(
    resources: IExecutionResources,
    config: ScanTypeConfig,
    repo_name: str,
    tool_name: str,
    segment: str,
    skip_reason: str,
) -> None:
    resources.event_sink.emit(
        se.ToolSkipped(
            run_id=config.run_id or 0,
            project_id=config.project_id,
            segment=segment,
            repo=repo_name,
            tool=tool_name,
            message=f"{tool_name} skipped: {skip_reason}",
            skip_reason=skip_reason,
        )
    )


class RepoScan(ScanType):
    """Run all applicable tools for a single repo."""

    def __init__(self, repo_name: str, exclude_tools: set[str] | None = None) -> None:
        self.repo_name = repo_name
        self.exclude_tools: set[str] = exclude_tools or set()

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        registry = cast(ToolRegistry, resources.registry)
        factory = cast(ToolWrapperFactory, resources.factory)
        executor = cast(ToolExecutor, resources.executor)

        repos = config.repo_repo.list_active() if config.repo_repo is not None else []
        repo = next((r for r in repos if r.name == self.repo_name), None)
        if repo is None:
            raise ValueError(
                f"Repository '{self.repo_name}' not found in"
                f" project '{config.project_name}'"
            )

        services = repo.services if repo.services else []
        if not services:
            raise ValueError(f"Repository '{repo.name}' has no services")

        all_services_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        for service in services:
            tool_set: set[str] = set()
            for registered_tool in cast(list[Any], registry.get_all_tools()):
                if registered_tool.always_run:
                    tool_set.add(registered_tool.name)
                elif registered_tool.language_gates:
                    if getattr(registered_tool, "scan_segment", "") == "sca":
                        skip, _ = should_skip_sca_tool(
                            registered_tool, service, repo.path
                        )
                        if not skip:
                            tool_set.add(registered_tool.name)
                    else:
                        gates = [g.lower() for g in registered_tool.language_gates]
                        for lang in service.languages or []:
                            if lang.lower() in gates:
                                tool_set.add(registered_tool.name)
                                break

            if noir_skip_reason(service, repo.path) is not None:
                tool_set.discard("noir")

            ordered_tools = ordered_repo_tools(tool_set, registry)
            if self.exclude_tools:
                ordered_tools = [
                    t for t in ordered_tools if t not in self.exclude_tools
                ]

            lang_str = ", ".join(service.languages) if service.languages else "unknown"
            service_label = repo.name
            if len(services) > 1:
                service_label = f"{repo.name} [{service.name}]"
            resources.display.print_repo_scan_header(
                service_label, lang_str, ordered_tools
            )

            start = perf_counter()
            results: list[ToolResult] = []

            for _tool_idx, tool_name in enumerate(ordered_tools):
                tool_inst_for_seg: Any = registry.get_tool(tool_name)
                seg = (
                    getattr(tool_inst_for_seg, "scan_segment", "")
                    if tool_inst_for_seg is not None
                    else ""
                )

                tool_config = registry.resolve_tool_config(
                    tool_name,
                    repo_id=repo.id,
                    service_name=service.name,
                )
                if tool_config is None:
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                    )
                    _emit_skipped(
                        resources,
                        config,
                        self.repo_name,
                        tool_name,
                        seg,
                        "not registered",
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
                    _emit_skipped(
                        resources,
                        config,
                        self.repo_name,
                        tool_name,
                        seg,
                        "factory error",
                    )
                    total_skipped += 1
                    continue

                if tool.requires_base_urls and not service.base_urls:
                    resources.display.print_tool_line(
                        ToolDisplayRow(
                            tool_name, False, True, 0, 0.0, "no base_urls configured"
                        )
                    )
                    _emit_skipped(
                        resources,
                        config,
                        self.repo_name,
                        tool_name,
                        seg,
                        "no base_urls configured",
                    )
                    total_skipped += 1
                    continue

                if not tool.check_available():
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not installed")
                    )
                    _emit_skipped(
                        resources,
                        config,
                        self.repo_name,
                        tool_name,
                        seg,
                        "not installed",
                    )
                    total_skipped += 1
                    continue

                resources.display.print_running(tool_name)
                resources.event_sink.emit(
                    se.ToolStarted(
                        run_id=config.run_id or 0,
                        project_id=config.project_id,
                        segment=seg,
                        repo=repo.name,
                        tool=tool_name,
                        message=f"{tool_name} on {repo.name} started",
                    )
                )
                context = make_context(
                    config.tool_config,
                    config.project_name,
                    config.base_path,
                    registry,
                    repo,
                    service,
                    tool_config,
                )
                _remaining = (
                    len(ordered_tools) - _tool_idx - 1
                ) + config.remaining_peers
                result = execute_tool_passes(
                    tool,
                    context,
                    config,
                    executor,
                    remaining_tools=_remaining,
                    command_config=tool_config,
                )

                if result is None:
                    resources.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0)
                    )
                    _emit_skipped(
                        resources, config, self.repo_name, tool_name, seg, "no result"
                    )
                    total_skipped += 1
                else:
                    result = normalize_success(result, tool)
                    result.repo = self.repo_name
                    results.append(result)
                    if result.success:
                        total_run += 1
                        ingested = dispatch_and_count_ingested(
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
                        total_ingested += ingested
                        findings_by_tool[result.tool_name] = (
                            findings_by_tool.get(result.tool_name, 0) + ingested
                        )
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name,
                                True,
                                False,
                                ingested,
                                result.duration_seconds,
                            )
                        )
                        resources.event_sink.emit(
                            se.ToolCompleted(
                                run_id=config.run_id or 0,
                                project_id=config.project_id,
                                segment=seg,
                                repo=repo.name,
                                tool=tool_name,
                                message=(f"{tool_name} on {repo.name} complete"),
                                findings_count=ingested,
                                duration=result.duration_seconds,
                                exit_code=0,
                            )
                        )
                        if tool_name == "noir" and ingested == 0:
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
                                tool_name, False, False, 0, result.duration_seconds
                            )
                        )
                        resources.event_sink.emit(
                            se.ToolFailed(
                                run_id=config.run_id or 0,
                                project_id=config.project_id,
                                segment=seg,
                                repo=repo.name,
                                tool=tool_name,
                                message=f"{tool_name} on {repo.name} failed",
                                exit_code=1,
                                duration=result.duration_seconds,
                            )
                        )

            all_services_results.extend(results)

        duration = round(perf_counter() - start, 1)

        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=findings_by_tool.get(r.tool_name, 0),
                duration_seconds=r.duration_seconds,
                repo=r.repo,
            )
            for r in all_services_results
        ]
        resources.display.print_summary_table(rows)
        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_services_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
        resources.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary
