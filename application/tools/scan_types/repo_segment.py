"""RepoSegmentScan — runs a set of tools on every configured repository."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from application.tools.scan_types._helpers import (
    _dispatch_and_count_ingested,
    _execute_tool_passes,
    _make_context,
    _normalize_success,
)
from application.tools.scan_types.resources import ExecutionResources
from domain.pipeline.events import ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.base import ScanType
from domain.tools.scan_types.models import ScanSummary, ScanTypeConfig

logger = logging.getLogger(__name__)


class RepoSegmentScan(ScanType):
    """Run a set of tools on every configured repository."""

    def __init__(self, tool_names: list[str]) -> None:
        self.tool_names = tool_names

    def execute(
        self, config: ScanTypeConfig, resources: ExecutionResources
    ) -> ScanSummary:
        start = perf_counter()
        repos = config.config_manager.load_repositories(config.project_name)
        if not repos:
            config.display.print_status(
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

        _reg_tools: list[Any] = resources.registry.get_all_tools()
        _lang_specific: set[str] = {
            t.name for t in _reg_tools if t.name in self.tool_names and t.language_gates
        }

        _total_invocations = len(repos) * len(self.tool_names)
        _invocation = 0

        for repo in repos:
            config.display.print_status(f"  [bold]Repository:[/bold] {repo.name}")
            repo_results: list[ToolResult] = []

            for tool_name in self.tool_names:
                _invocation += 1
                if tool_name in _lang_specific:
                    repo_langs = {lang.lower() for lang in (repo.languages or [])}
                    tool_inst: Any = resources.registry.get_tool(tool_name)
                    gates = (
                        [g.lower() for g in tool_inst.language_gates]
                        if tool_inst is not None
                        else []
                    )
                    if not any(lang in gates for lang in repo_langs):
                        config.display.print_tool_line(
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

                tool_config = resources.registry.get_tool_config(tool_name)
                if tool_config is None:
                    config.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                    )
                    total_skipped += 1
                    continue

                try:
                    tool: Any = resources.factory.create(tool_name, tool_config)
                except Exception as exc:
                    logger.warning("Factory failed for %r: %s", tool_name, exc)
                    config.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "factory error")
                    )
                    total_skipped += 1
                    continue

                if tool.requires_base_urls and not repo.base_urls:
                    config.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "no base_urls")
                    )
                    total_skipped += 1
                    continue

                if not tool.check_available():
                    config.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not installed")
                    )
                    total_skipped += 1
                    continue

                config.display.print_running(tool_name, repo.name)
                context = _make_context(
                    config.config_manager,
                    config.project_name,
                    config.base_path,
                    resources.registry,
                    repo,
                    tool_config,
                )
                _remaining = (_total_invocations - _invocation) + config.remaining_peers
                result = _execute_tool_passes(
                    tool,
                    context,
                    config,
                    resources.executor,
                    remaining_tools=_remaining,
                )

                if result is None:
                    config.display.print_tool_line(
                        ToolDisplayRow(f"{tool_name}/{repo.name}", False, True, 0, 0.0)
                    )
                    total_skipped += 1
                else:
                    result = _normalize_success(result, tool)
                    repo_results.append(result)
                    findings = tool.count_findings(result.parsed_data or {})
                    findings_by_tool[result.tool_name] = (
                        findings_by_tool.get(result.tool_name, 0) + findings
                    )
                    if result.success:
                        total_run += 1
                        config.display.print_tool_line(
                            ToolDisplayRow(
                                f"{tool_name}/{repo.name}",
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
                                f"{tool_name}/{repo.name}",
                                False,
                                False,
                                0,
                                result.duration_seconds,
                            )
                        )

            all_results.extend(repo_results)
            for r in repo_results:
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

        return ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=round(perf_counter() - start, 1),
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
