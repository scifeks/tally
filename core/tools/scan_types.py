"""ScanType abstractions: constants, shared helpers, and concrete scan classes.

Phase 6 extraction — all scan logic that previously lived in
``ScanOrchestrator`` private methods now lives here as concrete
``ScanType`` subclasses.  ``orchestrator.py`` is reduced to a thin shim
that constructs a ``ScanTypeConfig`` and delegates to these classes.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING, Any, cast

from core.pipeline.events import EventBus, ToolCompleted
from core.tools.base import ToolResult
from core.tools.display import OrchestratorDisplay, ToolDisplayRow
from core.tools.exceptions import InvalidSegmentError
from core.tools.executor import ToolExecutor
from core.tools.factory import ToolWrapperFactory
from core.tools.interface import ExecutionContext, ToolInterface
from core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from core.config.manager import ConfigManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

SEGMENT_ORDER: list[str] = ["network", "sast", "sca", "secrets", "api"]


# ---------------------------------------------------------------------------
# ScanSummary — canonical definition; re-exported by orchestrator.py
# ---------------------------------------------------------------------------


@dataclass
class ScanSummary:
    total_tools_run: int
    total_tools_skipped: int
    total_tools_failed: int
    results: list[ToolResult]
    duration_seconds: float
    findings_ingested: int
    findings_by_tool: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ScanTypeConfig — everything a ScanType needs at execute-time
# ---------------------------------------------------------------------------


@dataclass
class ScanTypeConfig:
    project_name: str
    base_path: str
    executor: ToolExecutor
    registry: ToolRegistry
    config_manager: ConfigManager
    event_bus: EventBus
    display: OrchestratorDisplay
    run_id: int | None
    auto_approve: bool = False
    factory: ToolWrapperFactory = field(default_factory=ToolWrapperFactory)


# ---------------------------------------------------------------------------
# ToolRun — introspection dataclass (unused by execute() but part of API)
# ---------------------------------------------------------------------------


@dataclass
class ToolRun:
    tool_interface: ToolInterface
    profile: str
    remaining: int


# ---------------------------------------------------------------------------
# Shared helpers (transplanted from ScanOrchestrator private methods)
# ---------------------------------------------------------------------------


def _make_context(
    config_manager: ConfigManager,
    project_name: str,
    base_path: str,
    registry: ToolRegistry,
    repo: Any,
    tool_config: Any,
) -> ExecutionContext:
    return ExecutionContext(
        project_name=project_name,
        base_path=base_path,
        repo=repo,
        config_manager=config_manager,
        registry=registry,
        is_docker=(tool_config.location == "docker" if tool_config else False),
        execution_mode="scan",
    )


def _execute_tool_passes(
    tool: ToolInterface,
    context: ExecutionContext,
    scan_config: ScanTypeConfig,
) -> ToolResult | None:
    """Prompt approval once, run all ExecutionPasses, return merged result."""
    if not scan_config.auto_approve:
        try:
            answer = input(f"Run {tool.name}? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer not in ("y", "yes"):
            return None
        try:
            all_ans = input("Approve all remaining? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
        else:
            if all_ans in ("y", "yes"):
                scan_config.auto_approve = True

    passes = tool.build_execution_passes(context)
    pass_results = [scan_config.executor.run(p, tool) for p in passes]
    return tool.merge_pass_results(pass_results)


def _normalize_success(result: ToolResult, tool: ToolInterface) -> ToolResult:
    """Mark tools that exit non-zero on findings as successful when
    parsed_data is valid.
    """
    if tool.findings_exit_ok:
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True
    return result


def _tools_for_segment(segment: str, registry: ToolRegistry) -> list[str]:
    """Return tool names registered under the given scan segment."""
    tools: list[Any] = registry.get_all_tools()
    return [t.name for t in tools if t.scan_segment == segment]


def _ordered_repo_tools(tool_set: set[str], registry: ToolRegistry) -> list[str]:
    """Order tool_set by SEGMENT_ORDER, then alphabetically within each segment."""
    result: list[str] = []
    for segment in SEGMENT_ORDER:
        if segment == "network":
            continue
        tools_in_seg = sorted(
            name
            for name in tool_set
            if registry.get_tool(name) is not None
            and cast(Any, registry.get_tool(name)).scan_segment == segment
        )
        result.extend(tools_in_seg)
    return result


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ScanType(ABC):
    @abstractmethod
    def execute(self, config: ScanTypeConfig) -> ScanSummary: ...


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class NetworkSegmentScan(ScanType):
    """Run nmap for all configured profiles as a single merged result."""

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
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

        tool_config = config.registry.get_tool_config("nmap")
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
            tool: Any = config.factory.create("nmap", tool_config)
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
            config.registry,
            None,
            tool_config,
        )
        result = _execute_tool_passes(tool, context, config)

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


class SegmentScan(ScanType):
    """Validate a segment name and delegate to the appropriate scan type."""

    def __init__(self, segment_name: str) -> None:
        self.segment_name = segment_name

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
        _all_tools: list[Any] = config.registry.get_all_tools()
        valid_segments = {t.scan_segment for t in _all_tools}
        if self.segment_name not in valid_segments:
            raise InvalidSegmentError(self.segment_name, sorted(valid_segments))
        if self.segment_name == "network":
            return NetworkSegmentScan().execute(config)
        return RepoSegmentScan(
            _tools_for_segment(self.segment_name, config.registry)
        ).execute(config)


class RepoSegmentScan(ScanType):
    """Run a set of tools on every configured repository."""

    def __init__(self, tool_names: list[str]) -> None:
        self.tool_names = tool_names

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
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

        _reg_tools: list[Any] = config.registry.get_all_tools()
        _lang_specific: set[str] = {
            t.name for t in _reg_tools if t.name in self.tool_names and t.language_gates
        }

        for repo in repos:
            config.display.print_status(f"  [bold]Repository:[/bold] {repo.name}")
            repo_results: list[ToolResult] = []

            for tool_name in self.tool_names:
                if tool_name in _lang_specific:
                    repo_langs = {lang.lower() for lang in (repo.languages or [])}
                    tool_inst: Any = config.registry.get_tool(tool_name)
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

                tool_config = config.registry.get_tool_config(tool_name)
                if tool_config is None:
                    config.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                    )
                    total_skipped += 1
                    continue

                try:
                    tool: Any = config.factory.create(tool_name, tool_config)
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
                    config.registry,
                    repo,
                    tool_config,
                )
                result = _execute_tool_passes(tool, context, config)

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
                config.event_bus.dispatch(
                    ToolCompleted(
                        r,
                        repo.name,
                        config.run_id,
                        config.project_name,
                        config.base_path,
                    )
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


class RepoScan(ScanType):
    """Run all applicable tools for a single repo."""

    def __init__(self, repo_name: str) -> None:
        self.repo_name = repo_name

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
        repos = config.config_manager.load_repositories(config.project_name)
        repo = next((r for r in repos if r.name == self.repo_name), None)
        if repo is None:
            raise ValueError(
                f"Repository '{self.repo_name}' not found in"
                f" project '{config.project_name}'"
            )

        tool_set: set[str] = set()
        for registered_tool in cast(list[Any], config.registry.get_all_tools()):
            if registered_tool.always_run:
                tool_set.add(registered_tool.name)
            elif registered_tool.language_gates:
                gates = [g.lower() for g in registered_tool.language_gates]
                for lang in repo.languages or []:
                    if lang.lower() in gates:
                        tool_set.add(registered_tool.name)
                        break

        ordered_tools = _ordered_repo_tools(tool_set, config.registry)

        lang_str = ", ".join(repo.languages) if repo.languages else "unknown"
        config.display.print_repo_scan_header(repo.name, lang_str, ordered_tools)

        start = perf_counter()
        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = 0
        findings_by_tool: dict[str, int] = {}

        for tool_name in ordered_tools:
            tool_config = config.registry.get_tool_config(tool_name)
            if tool_config is None:
                config.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                )
                total_skipped += 1
                continue

            try:
                tool: Any = config.factory.create(tool_name, tool_config)
            except Exception as exc:
                logger.warning("Factory failed for %r: %s", tool_name, exc)
                config.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0, "factory error")
                )
                total_skipped += 1
                continue

            if tool.requires_base_urls and not repo.base_urls:
                config.display.print_tool_line(
                    ToolDisplayRow(
                        tool_name, False, True, 0, 0.0, "no base_urls configured"
                    )
                )
                total_skipped += 1
                continue

            if not tool.check_available():
                config.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0, "not installed")
                )
                total_skipped += 1
                continue

            config.display.print_running(tool_name)
            context = _make_context(
                config.config_manager,
                config.project_name,
                config.base_path,
                config.registry,
                repo,
                tool_config,
            )
            result = _execute_tool_passes(tool, context, config)

            if result is None:
                config.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0)
                )
                total_skipped += 1
            else:
                result = _normalize_success(result, tool)
                results.append(result)
                findings = tool.count_findings(result.parsed_data or {})
                findings_by_tool[result.tool_name] = (
                    findings_by_tool.get(result.tool_name, 0) + findings
                )
                if result.success:
                    total_run += 1
                    config.display.print_tool_line(
                        ToolDisplayRow(
                            tool_name,
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
                            tool_name, False, False, 0, result.duration_seconds
                        )
                    )

        duration = round(perf_counter() - start, 1)
        for r in results:
            config.event_bus.dispatch(
                ToolCompleted(
                    r,
                    repo.name,
                    config.run_id,
                    config.project_name,
                    config.base_path,
                )
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
            findings_ingested=0,
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


class ToolOnRepoScan(ScanType):
    """Run a single tool against one named repository."""

    def __init__(self, tool_name: str, repo_name: str) -> None:
        self.tool_name = tool_name
        self.repo_name = repo_name

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
        repos = config.config_manager.load_repositories(config.project_name)
        repo = next(
            (r for r in repos if r.name.lower() == self.repo_name.lower()), None
        )
        if repo is None:
            raise ValueError(
                f"Repository '{self.repo_name}' not found in"
                f" project '{config.project_name}'"
            )

        tool_config = config.registry.get_tool_config(self.tool_name)
        if tool_config is None:
            raise ValueError(f"Tool '{self.tool_name}' is not registered.")

        try:
            tool: Any = config.factory.create(self.tool_name, tool_config)
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
            config.registry,
            repo,
            tool_config,
        )
        result = _execute_tool_passes(tool, context, config)

        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = 0
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
            config.event_bus.dispatch(
                ToolCompleted(
                    r,
                    repo.name,
                    config.run_id,
                    config.project_name,
                    config.base_path,
                )
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
            findings_ingested=0,
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


class FullScan(ScanType):
    """Run all segments across all repos in SEGMENT_ORDER."""

    def __init__(self, exclude_segments: list[str] | None = None) -> None:
        self.exclude_segments = exclude_segments or []

    def execute(self, config: ScanTypeConfig) -> ScanSummary:
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
                seg_summary = NetworkSegmentScan().execute(config)
            else:
                seg_summary = RepoSegmentScan(
                    _tools_for_segment(segment, config.registry)
                ).execute(config)

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
