"""Scan orchestration: coordinate multi-tool scans across segments and repositories."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING, Any

from core.pipeline.events import EventBus, ToolCompleted
from core.tools.base import ToolResult
from core.tools.display import OrchestratorDisplay, ToolDisplayRow
from core.tools.executor import ToolExecutor
from core.tools.factory import ToolWrapperFactory
from core.tools.interface import ExecutionContext, ToolInterface
from core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (exported for smoke tests and REPL use)
# ---------------------------------------------------------------------------

SCAN_SEGMENTS: dict[str, list[str]] = {
    "network": ["nmap"],
    "sast": ["semgrep"],
    "sca": ["osv-scanner", "pip-audit", "npm-audit", "composer-audit"],
    "secrets": ["gitleaks"],
    "api": ["zap"],
}

SEGMENT_ORDER: list[str] = ["network", "sast", "sca", "secrets", "api"]

LANGUAGE_TOOL_MAP: dict[str, list[str]] = {
    "python": ["pip-audit"],
    "javascript": ["npm-audit"],
    "typescript": ["npm-audit"],
    "node": ["npm-audit"],
    "php": ["composer-audit"],
}

ALWAYS_RUN_REPO_TOOLS: list[str] = ["semgrep", "osv-scanner", "gitleaks", "zap"]

# Tools that exit non-zero when findings are present (not true failures)
_FINDINGS_EXIT_TOOLS: frozenset = frozenset(
    {
        "semgrep",
        "osv-scanner",
        "pip-audit",
        "npm-audit",
        "composer-audit",
        "gitleaks",
        "zap",
    }
)

# Canonical ordering for repo-scan tool execution
_REPO_TOOL_ORDER: list[str] = [
    "semgrep",
    "osv-scanner",
    "pip-audit",
    "npm-audit",
    "composer-audit",
    "gitleaks",
    "zap",
]


# ---------------------------------------------------------------------------
# ScanSummary
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
# ScanOrchestrator
# ---------------------------------------------------------------------------


class ScanOrchestrator:
    """Coordinate multi-tool scans across segments and repositories.

    Args:
        project:        Active project name.
        tool_registry:  Registry of available tool wrappers.
        tool_executor:  Configured executor (carries base_path and project_name).
        event_bus:      EventBus for dispatching ToolCompleted events.
        run_id:         Optional run ID forwarded through events.
        factory:        Optional ToolWrapperFactory; defaults to a fresh instance.
        console:        Optional Rich console for display output.
    """

    def __init__(
        self,
        project: str,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        event_bus: EventBus,
        run_id: int | None = None,
        factory: ToolWrapperFactory | None = None,
        console: Console | None = None,
    ) -> None:
        self.project_name = project
        self.registry = tool_registry
        self.executor = tool_executor
        self._event_bus = event_bus
        self._run_id = run_id
        self.display = OrchestratorDisplay(console=console)
        self._auto_approve: bool = False
        self._factory = factory or ToolWrapperFactory()

        from core.config.manager import ConfigManager

        self._config = ConfigManager(str(tool_executor.base_path))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_full_scan(
        self,
        auto_approve: bool = False,
        exclude_segments: list[str] | None = None,
    ) -> ScanSummary:
        """Run all segments across all repos in SEGMENT_ORDER.

        The network segment runs once at project level; all other segments
        run per configured repository.
        """
        exclude_segments = exclude_segments or []
        start = perf_counter()

        all_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        merged_fbt: dict[str, int] = {}

        self.display.print_scan_header(f"Full Scan: {self.project_name}")

        for segment in SEGMENT_ORDER:
            if segment in exclude_segments:
                self.display.print_status(f"[dim]Skipping segment: {segment}[/dim]")
                continue

            self.display.print_segment_header(segment)
            seg_summary = self.run_segment(segment, auto_approve=auto_approve)

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
        self.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=merged_fbt,
        )
        self.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary

    def run_segment(
        self,
        segment_name: str,
        auto_approve: bool = False,
    ) -> ScanSummary:
        """Run a single segment across all repos (or project-level for network).

        Raises:
            ValueError: If segment_name is not in SCAN_SEGMENTS.
        """
        if segment_name not in SCAN_SEGMENTS:
            raise ValueError(
                f"Unknown segment: {segment_name!r}. "
                f"Valid segments: {list(SCAN_SEGMENTS)}"
            )

        start = perf_counter()
        all_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0

        findings_by_tool: dict[str, int] = {}
        if segment_name == "network":
            (
                results_list,
                total_run,
                total_skipped,
                total_failed,
                total_ingested,
                findings_by_tool,
            ) = self._run_network_segment(auto_approve)
            all_results.extend(results_list)
        else:
            (
                results_list,
                total_run,
                total_skipped,
                total_failed,
                total_ingested,
                findings_by_tool,
            ) = self._run_repo_segment(SCAN_SEGMENTS[segment_name], auto_approve)
            all_results.extend(results_list)

        duration = round(perf_counter() - start, 1)
        return ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )

    def run_repo_scan(
        self,
        repo_name: str,
        auto_approve: bool = False,
        exclude_dirs: list[str] | None = None,
        severity_filter: str | None = None,
    ) -> ScanSummary:
        """Run all applicable tools for a single repo.

        Tool selection:
        - Always includes ALWAYS_RUN_REPO_TOOLS
        - Adds language-specific tools from LANGUAGE_TOOL_MAP
        - Never includes nmap

        Args:
            repo_name:       Repository name as configured in the project.
            auto_approve:    Skip per-tool approval prompts.
            exclude_dirs:    Directories to exclude (passed to supporting tools).
            severity_filter: Minimum severity level (critical/high/medium/low).

        Raises:
            ValueError: If repo_name is not found in the active project.
        """
        repos = self._config.load_repositories(self.project_name)
        repo = next((r for r in repos if r.name == repo_name), None)
        if repo is None:
            raise ValueError(
                f"Repository '{repo_name}' not found in project '{self.project_name}'"
            )

        # Build ordered tool list
        tool_set: set = set(ALWAYS_RUN_REPO_TOOLS)
        for lang in repo.languages or []:
            tool_set.update(LANGUAGE_TOOL_MAP.get(lang.lower(), []))

        ordered_tools = [t for t in _REPO_TOOL_ORDER if t in tool_set]

        lang_str = ", ".join(repo.languages) if repo.languages else "unknown"
        self.display.print_repo_scan_header(repo.name, lang_str, ordered_tools)

        start = perf_counter()
        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = 0
        findings_by_tool: dict[str, int] = {}

        for idx, tool_name in enumerate(ordered_tools):
            config = self.registry.get_tool_config(tool_name)
            if config is None:
                self.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                )
                total_skipped += 1
                continue

            try:
                tool: Any = self._factory.create(tool_name, config)
            except Exception as exc:
                logger.warning("Factory failed for %r: %s", tool_name, exc)
                self.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0, "factory error")
                )
                total_skipped += 1
                continue

            if tool.requires_base_urls and not repo.base_urls:
                self.display.print_tool_line(
                    ToolDisplayRow(
                        tool_name, False, True, 0, 0.0, "no base_urls configured"
                    )
                )
                total_skipped += 1
                continue

            if not tool.check_available():
                self.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0, "not installed")
                )
                total_skipped += 1
                continue

            self.display.print_running(tool_name)
            context = self._make_context(repo, config)
            result = self._execute_tool_passes(tool, context, auto_approve)

            if result is None:
                self.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, True, 0, 0.0)
                )
                total_skipped += 1
            else:
                result = self._normalize_success(result)
                results.append(result)
                findings = tool.count_findings(result.parsed_data or {})
                findings_by_tool[result.tool_name] = (
                    findings_by_tool.get(result.tool_name, 0) + findings
                )
                if result.success:
                    total_run += 1
                    self.display.print_tool_line(
                        ToolDisplayRow(
                            tool_name, True, False, findings, result.duration_seconds
                        )
                    )
                else:
                    total_failed += 1
                    self.display.print_tool_line(
                        ToolDisplayRow(
                            tool_name, False, False, 0, result.duration_seconds
                        )
                    )

        duration = round(perf_counter() - start, 1)
        for r in results:
            self._event_bus.dispatch(
                ToolCompleted(
                    r,
                    repo.name,
                    self._run_id,
                    self.project_name,
                    str(self.executor.base_path),
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
        self.display.print_summary_table(rows)
        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results,
            duration_seconds=duration,
            findings_ingested=0,
            findings_by_tool=findings_by_tool,
        )
        self.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary

    def run_tool_on_all_repos(
        self,
        tool_name: str,
        auto_approve: bool = False,
    ) -> ScanSummary:
        """Run a single tool against all configured repositories.

        Args:
            tool_name:    Name of the tool to run (must be registered and not 'nmap').
            auto_approve: Skip per-tool approval prompts.

        Returns:
            ScanSummary aggregating results across all repositories.
        """
        start = perf_counter()

        self.display.print_scan_header(
            f"Repo Tool Scan: {self.project_name} — {tool_name}"
        )

        (
            results_list,
            total_run,
            total_skipped,
            total_failed,
            total_ingested,
            findings_by_tool,
        ) = self._run_repo_segment([tool_name], auto_approve)

        duration = round(perf_counter() - start, 1)
        rows = [
            ToolDisplayRow(
                tool_name=r.tool_name,
                success=r.success,
                skipped=False,
                finding_count=findings_by_tool.get(r.tool_name, 0),
                duration_seconds=r.duration_seconds,
            )
            for r in results_list
        ]
        self.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results_list,
            duration_seconds=duration,
            findings_ingested=total_ingested,
            findings_by_tool=findings_by_tool,
        )
        self.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary

    def run_tool_on_repo(
        self,
        tool_name: str,
        repo_name: str,
        auto_approve: bool = False,
    ) -> ScanSummary:
        """Run a single tool against one named repository.

        Args:
            tool_name:    Registered tool name (not 'nmap').
            repo_name:    Repository name (case-insensitive match).
            auto_approve: Skip approval prompt.

        Raises:
            ValueError: If repo or tool not found, or tool unavailable.
        """
        repos = self._config.load_repositories(self.project_name)
        repo = next((r for r in repos if r.name.lower() == repo_name.lower()), None)
        if repo is None:
            raise ValueError(
                f"Repository '{repo_name}' not found in project '{self.project_name}'"
            )

        config = self.registry.get_tool_config(tool_name)
        if config is None:
            raise ValueError(f"Tool '{tool_name}' is not registered.")

        try:
            tool: Any = self._factory.create(tool_name, config)
        except Exception as exc:
            raise ValueError(f"Tool '{tool_name}' factory error: {exc}") from exc

        if not tool.check_available():
            raise ValueError(f"Tool '{tool_name}' is not installed.")

        self.display.print_scan_header(f"Repo Tool Scan: {repo.name} — {tool_name}")

        start = perf_counter()
        context = self._make_context(repo, config)
        result = self._execute_tool_passes(tool, context, auto_approve)

        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = 0
        findings_by_tool: dict[str, int] = {}

        if result is None:
            self.display.print_tool_line(ToolDisplayRow(tool_name, False, True, 0, 0.0))
            total_skipped += 1
        else:
            result = self._normalize_success(result)
            results.append(result)
            findings = tool.count_findings(result.parsed_data or {})
            findings_by_tool = {result.tool_name: findings}
            if result.success:
                total_run += 1
                self.display.print_tool_line(
                    ToolDisplayRow(
                        tool_name, True, False, findings, result.duration_seconds
                    )
                )
            else:
                total_failed += 1
                self.display.print_tool_line(
                    ToolDisplayRow(tool_name, False, False, 0, result.duration_seconds)
                )

        duration = round(perf_counter() - start, 1)
        for r in results:
            self._event_bus.dispatch(
                ToolCompleted(
                    r,
                    repo.name,
                    self._run_id,
                    self.project_name,
                    str(self.executor.base_path),
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
        self.display.print_summary_table(rows)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results,
            duration_seconds=duration,
            findings_ingested=0,
            findings_by_tool=findings_by_tool,
        )
        self.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=summary.total_tools_skipped,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary

    # ------------------------------------------------------------------
    # Private — context and execution helpers
    # ------------------------------------------------------------------

    def _make_context(self, repo: Any, config: Any) -> ExecutionContext:
        return ExecutionContext(
            project_name=self.project_name,
            base_path=str(self.executor.base_path),
            repo=repo,
            config_manager=self._config,
            registry=self.registry,
            is_docker=(config.location == "docker" if config else False),
            execution_mode="scan",
        )

    def _execute_tool_passes(
        self,
        tool: ToolInterface,
        context: ExecutionContext,
        auto_approve: bool,
    ) -> ToolResult | None:
        """Prompt approval once, run all ExecutionPasses, return merged result."""
        if not auto_approve and not self._auto_approve:
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
                    self._auto_approve = True

        passes = tool.build_execution_passes(context)
        pass_results = [self.executor.run(p, tool) for p in passes]
        return tool.merge_pass_results(pass_results)

    # ------------------------------------------------------------------
    # Private — segment runners
    # ------------------------------------------------------------------

    def _run_network_segment(
        self,
        auto_approve: bool,
    ) -> tuple[list[ToolResult], int, int, int, int, dict[str, int]]:
        """Run nmap for all configured profiles as a single merged result.

        Returns (results, run, skipped, failed, ingested, findings_by_tool).
        """
        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        nmap_config = self._config.load_nmap_hosts(self.project_name)
        profiles = nmap_config.profiles if nmap_config else {}
        if not profiles:
            self.display.print_status(
                "[yellow]No nmap profiles configured"
                " — skipping network segment[/yellow]"
            )
            total_skipped += 1
            return (
                results,
                total_run,
                total_skipped,
                total_failed,
                total_ingested,
                findings_by_tool,
            )

        config = self.registry.get_tool_config("nmap")
        if config is None:
            self.display.print_tool_line(
                ToolDisplayRow("nmap", False, True, 0, 0.0, "not registered")
            )
            total_skipped += 1
            return (
                results,
                total_run,
                total_skipped,
                total_failed,
                total_ingested,
                findings_by_tool,
            )

        try:
            tool: Any = self._factory.create("nmap", config)
        except Exception as exc:
            logger.warning("Factory failed for 'nmap': %s", exc)
            self.display.print_tool_line(
                ToolDisplayRow("nmap", False, True, 0, 0.0, "factory error")
            )
            total_skipped += 1
            return (
                results,
                total_run,
                total_skipped,
                total_failed,
                total_ingested,
                findings_by_tool,
            )

        if not tool.check_available():
            self.display.print_tool_line(
                ToolDisplayRow("nmap", False, True, 0, 0.0, "not installed")
            )
            total_skipped += 1
            return (
                results,
                total_run,
                total_skipped,
                total_failed,
                total_ingested,
                findings_by_tool,
            )

        self.display.print_running("nmap")
        context = self._make_context(None, config)
        result = self._execute_tool_passes(tool, context, auto_approve)

        if result is None:
            self.display.print_tool_line(ToolDisplayRow("nmap", False, True, 0, 0.0))
            total_skipped += 1
        else:
            results.append(result)
            findings = tool.count_findings(result.parsed_data or {})
            findings_by_tool["nmap"] = findings_by_tool.get("nmap", 0) + findings
            if result.success:
                total_run += 1
                self.display.print_tool_line(
                    ToolDisplayRow(
                        "nmap", True, False, findings, result.duration_seconds
                    )
                )
                self._event_bus.dispatch(
                    ToolCompleted(
                        result,
                        self.project_name,
                        self._run_id,
                        self.project_name,
                        str(self.executor.base_path),
                    )
                )
            else:
                total_failed += 1
                self.display.print_tool_line(
                    ToolDisplayRow("nmap", False, False, 0, result.duration_seconds)
                )

        return (
            results,
            total_run,
            total_skipped,
            total_failed,
            total_ingested,
            findings_by_tool,
        )

    def _run_repo_segment(
        self,
        tool_names: list[str],
        auto_approve: bool,
    ) -> tuple[list[ToolResult], int, int, int, int, dict[str, int]]:
        """Run a set of tools on every configured repository.

        Returns (results, run, skipped, failed, ingested, findings_by_tool).
        """
        repos = self._config.load_repositories(self.project_name)
        if not repos:
            self.display.print_status(
                "[yellow]No repositories configured — skipping[/yellow]"
            )
            return [], 0, len(tool_names), 0, 0, {}

        all_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0
        findings_by_tool: dict[str, int] = {}

        for repo in repos:
            self.display.print_status(f"  [bold]Repository:[/bold] {repo.name}")
            repo_results: list[ToolResult] = []

            _lang_specific: set[str] = {
                t for tools in LANGUAGE_TOOL_MAP.values() for t in tools
            }

            for idx, tool_name in enumerate(tool_names):
                if tool_name in _lang_specific:
                    repo_langs = {lang.lower() for lang in (repo.languages or [])}
                    allowed = {
                        t
                        for lang, tools in LANGUAGE_TOOL_MAP.items()
                        if lang in repo_langs
                        for t in tools
                    }
                    if tool_name not in allowed:
                        self.display.print_tool_line(
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

                config = self.registry.get_tool_config(tool_name)
                if config is None:
                    self.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not registered")
                    )
                    total_skipped += 1
                    continue

                try:
                    tool: Any = self._factory.create(tool_name, config)
                except Exception as exc:
                    logger.warning("Factory failed for %r: %s", tool_name, exc)
                    self.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "factory error")
                    )
                    total_skipped += 1
                    continue

                if tool.requires_base_urls and not repo.base_urls:
                    self.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "no base_urls")
                    )
                    total_skipped += 1
                    continue

                if not tool.check_available():
                    self.display.print_tool_line(
                        ToolDisplayRow(tool_name, False, True, 0, 0.0, "not installed")
                    )
                    total_skipped += 1
                    continue

                self.display.print_running(tool_name, repo.name)
                context = self._make_context(repo, config)
                result = self._execute_tool_passes(tool, context, auto_approve)

                if result is None:
                    self.display.print_tool_line(
                        ToolDisplayRow(f"{tool_name}/{repo.name}", False, True, 0, 0.0)
                    )
                    total_skipped += 1
                else:
                    result = self._normalize_success(result)
                    repo_results.append(result)
                    findings = tool.count_findings(result.parsed_data or {})
                    findings_by_tool[result.tool_name] = (
                        findings_by_tool.get(result.tool_name, 0) + findings
                    )
                    if result.success:
                        total_run += 1
                        self.display.print_tool_line(
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
                        self.display.print_tool_line(
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
                self._event_bus.dispatch(
                    ToolCompleted(
                        r,
                        repo.name,
                        self._run_id,
                        self.project_name,
                        str(self.executor.base_path),
                    )
                )

        return (
            all_results,
            total_run,
            total_skipped,
            total_failed,
            total_ingested,
            findings_by_tool,
        )

    # ------------------------------------------------------------------
    # Private — result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_success(result: ToolResult) -> ToolResult:
        """Mark tools that exit non-zero on findings as successful
        when parsed_data is valid.
        """
        if result.tool_name in _FINDINGS_EXIT_TOOLS:
            if result.parsed_data and "error" not in result.parsed_data:
                result.success = True
        return result
