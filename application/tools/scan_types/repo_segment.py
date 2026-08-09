"""RepoSegmentScan: runs a set of tools on every configured repository."""

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
    segment: str,
    repo_name: str,
    tool_name: str,
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


def _try_llm_extraction(
    config: ScanTypeConfig,
    resources: IExecutionResources,
    repo: Any,
    service: Any,
) -> int:
    """Run LLM endpoint extraction if configured and URL inventory empty."""
    if not config.tool_config.endpoint_extraction_enabled:
        return 0

    if repo is None or repo.id is None:
        return 0

    if not service or not service.base_urls:
        return 0

    from urllib.parse import urlparse

    from application.url_inventory.llm_extractor import (
        LlmEndpointExtractor,
    )
    from core.project_paths import ProjectPaths
    from infrastructure.llm.factory import get_llm_provider
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.url_findings import (
        UrlFindingRepository,
    )

    parsed = urlparse(service.base_urls[0])
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    protocol = parsed.scheme or "https"

    paths = ProjectPaths.from_canonical(config.base_path, config.project_name)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    url_repo = UrlFindingRepository(factory)

    existing = url_repo.list_for_repo(repo.id)
    if existing:
        return 0

    try:
        provider = get_llm_provider("endpoint_extraction", config.base_path)
    except ValueError:
        return 0

    extractor = LlmEndpointExtractor(provider, url_repo)

    excluded_dirs = []
    if hasattr(service, "excluded_dirs") and service.excluded_dirs:
        excluded_dirs = service.excluded_dirs

    count = extractor.extract_for_repo(
        repo_path=repo.path,
        repo_id=repo.id,
        run_id=config.run_id,
        host=host,
        port=port,
        protocol=protocol,
        excluded_dirs=excluded_dirs,
    )

    if count > 0:
        msg = f"    [green]LLM extracted {count} endpoints for {repo.name}[/green]"
        resources.display.print_status(msg)

    return count


class RepoSegmentScan(ScanType):
    """Run a set of tools on every configured repository."""

    def __init__(self, tool_names: list[str], segment_name: str = "") -> None:
        self.tool_names = tool_names
        self.segment_name = segment_name

    def execute(
        self, config: ScanTypeConfig, resources: IExecutionResources
    ) -> ScanSummary:
        registry = cast(ToolRegistry, resources.registry)
        factory = cast(ToolWrapperFactory, resources.factory)
        executor = cast(ToolExecutor, resources.executor)

        start = perf_counter()
        repos = config.repo_repo.list_active() if config.repo_repo is not None else []
        if not repos:
            resources.display.print_status(
                "[yellow]No repositories configured; skipping[/yellow]"
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
            changed_files: list[str] | None = None
            if config.since_commit and config.git_diff:
                try:
                    changed_files = config.git_diff.changed_files(
                        repo.path, config.since_commit
                    )
                    if not changed_files:
                        logger.info(
                            "No files changed in %s since %s; skipping",
                            repo.name,
                            config.since_commit,
                        )
                        continue
                except ValueError:
                    logger.warning(
                        "Could not resolve %s in %s; scanning all files",
                        config.since_commit,
                        repo.name,
                    )
            for service in repo.services:
                repo_label = repo.name
                if len(repo.services) > 1:
                    repo_label = f"{repo.name} [{service.name}]"
                resources.display.print_status(f"[bold]Repository:[/bold] {repo_label}")

                repo_results: list[ToolResult] = []

                for tool_name in self.tool_names:
                    _invocation += 1

                    if self.segment_name == "sca":
                        tool_inst_check: Any = registry.get_tool(tool_name)
                        skip_sca, skip_reason = should_skip_sca_tool(
                            tool_inst_check, service, repo.path
                        )
                        if skip_sca:
                            resources.display.print_tool_line(
                                ToolDisplayRow(
                                    tool_name,
                                    False,
                                    True,
                                    0,
                                    0.0,
                                    skip_reason,
                                )
                            )
                            _emit_skipped(
                                resources,
                                config,
                                self.segment_name,
                                repo.name,
                                tool_name,
                                skip_reason,
                            )
                            total_skipped += 1
                            continue
                    elif tool_name in _lang_specific:
                        service_langs = {
                            lang.lower() for lang in (service.languages or [])
                        }
                        tool_inst: Any = registry.get_tool(tool_name)
                        gates = (
                            [g.lower() for g in tool_inst.language_gates]
                            if tool_inst is not None
                            else []
                        )
                        if not any(lang in gates for lang in service_langs):
                            skip_reason = f"not applicable for {service.name} languages"
                            resources.display.print_tool_line(
                                ToolDisplayRow(
                                    tool_name,
                                    False,
                                    True,
                                    0,
                                    0.0,
                                    skip_reason,
                                )
                            )
                            _emit_skipped(
                                resources,
                                config,
                                self.segment_name,
                                repo.name,
                                tool_name,
                                skip_reason,
                            )
                            total_skipped += 1
                            continue

                    tool_config = registry.get_tool_config(tool_name)
                    if tool_config is None:
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name, False, True, 0, 0.0, "not registered"
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            "not registered",
                        )
                        total_skipped += 1
                        continue

                    try:
                        tool: Any = factory.create(tool_name, tool_config)
                    except Exception as exc:
                        logger.warning("Factory failed for %r: %s", tool_name, exc)
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name, False, True, 0, 0.0, "factory error"
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            "factory error",
                        )
                        total_skipped += 1
                        continue

                    if tool_name in ("noir", "katana") and not service.crawl_enabled:
                        skip_reason = "skipped (live crawling disabled)"
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name,
                                False,
                                True,
                                0,
                                0.0,
                                skip_reason,
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            skip_reason,
                        )
                        total_skipped += 1
                        continue

                    _noir_skip = noir_skip_reason(service, repo.path)
                    if tool_name == "noir" and _noir_skip is not None:
                        skip_reason = f"skipped ({_noir_skip})"
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name,
                                False,
                                True,
                                0,
                                0.0,
                                skip_reason,
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            skip_reason,
                        )
                        total_skipped += 1
                        _try_llm_extraction(config, resources, repo, service)
                        continue

                    if tool.requires_base_urls and not service.base_urls:
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name, False, True, 0, 0.0, "no base_urls"
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            "no base_urls",
                        )
                        total_skipped += 1
                        continue

                    if not tool.check_available():
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                tool_name, False, True, 0, 0.0, "not installed"
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            "not installed",
                        )
                        total_skipped += 1
                        continue

                    resources.display.print_running(tool_name, repo.name)
                    resources.event_sink.emit(
                        se.ToolStarted(
                            run_id=config.run_id or 0,
                            project_id=config.project_id,
                            segment=self.segment_name,
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
                        _total_invocations - _invocation
                    ) + config.remaining_peers
                    result = execute_tool_passes(
                        tool,
                        context,
                        config,
                        executor,
                        remaining_tools=_remaining,
                        command_config=tool_config,
                        changed_files=changed_files,
                    )

                    if result is None:
                        resources.display.print_tool_line(
                            ToolDisplayRow(
                                f"{tool_name}/{repo.name}", False, True, 0, 0.0
                            )
                        )
                        _emit_skipped(
                            resources,
                            config,
                            self.segment_name,
                            repo.name,
                            tool_name,
                            "no result",
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
                            resources.display.print_tool_line(
                                ToolDisplayRow(
                                    f"{tool_name}/{repo.name}",
                                    True,
                                    False,
                                    findings,
                                    result.duration_seconds,
                                )
                            )
                            resources.event_sink.emit(
                                se.ToolCompleted(
                                    run_id=config.run_id or 0,
                                    project_id=config.project_id,
                                    segment=self.segment_name,
                                    repo=repo.name,
                                    tool=tool_name,
                                    message=f"{tool_name} on {repo.name} complete",
                                    findings_count=findings,
                                    duration=result.duration_seconds,
                                    exit_code=0,
                                )
                            )
                            if tool_name == "noir" and findings == 0:
                                resources.display.print_status(
                                    "    [yellow]⚠ noir found 0 endpoints. "
                                    "Framework not supported by noir.[/yellow]"
                                )
                                resources.display.print_status(
                                    "    [dim]ZAP will fall back to spider-only "
                                    "mode for this repository.[/dim]"
                                )
                                _try_llm_extraction(config, resources, repo, service)
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
                        else:
                            total_failed += 1
                            resources.display.print_tool_line(
                                ToolDisplayRow(
                                    f"{tool_name}/{repo.name}",
                                    False,
                                    False,
                                    0,
                                    result.duration_seconds,
                                )
                            )
                            resources.event_sink.emit(
                                se.ToolFailed(
                                    run_id=config.run_id or 0,
                                    project_id=config.project_id,
                                    segment=self.segment_name,
                                    repo=repo.name,
                                    tool=tool_name,
                                    message=f"{tool_name} on {repo.name} failed",
                                    exit_code=1,
                                    duration=result.duration_seconds,
                                )
                            )
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
