"""Scan orchestration: coordinate multi-tool scans across segments and repositories."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from rich.console import Console
from rich.table import Table

from core.tools.base import ToolResult, ToolWrapper
from core.tools.executor import ToolExecutor
from core.tools.parsers.gitleaks_parser import combine_gitleaks_results
from core.tools.registry import ToolRegistry

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


# ---------------------------------------------------------------------------
# ScanOrchestrator
# ---------------------------------------------------------------------------


class ScanOrchestrator:
    """Coordinate multi-tool scans across segments and repositories.

    Args:
        project:        Active project name.
        tool_registry:  Registry of available tool wrappers.
        tool_executor:  Configured executor (carries base_path and project_name).
        rag_engine:     Optional RAGEngine for ingestion. None disables ingestion.
    """

    def __init__(
        self,
        project: str,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        rag_engine: object,  # Optional[RAGEngine] — avoid import cycle at module level
    ) -> None:
        self.project_name = project
        self.registry = tool_registry
        self.executor = tool_executor
        self.rag_engine = rag_engine
        self.console = Console()

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

        self.console.print(f"\n[bold cyan]Full Scan:[/bold cyan] {self.project_name}")
        self.console.print("─" * 50)

        for segment in SEGMENT_ORDER:
            if segment in exclude_segments:
                self.console.print(f"[dim]Skipping segment: {segment}[/dim]")
                continue

            self.console.print(f"\n[bold yellow]{segment.upper()}[/bold yellow]")
            seg_summary = self.run_segment(segment, auto_approve=auto_approve)

            all_results.extend(seg_summary.results)
            total_run += seg_summary.total_tools_run
            total_skipped += seg_summary.total_tools_skipped
            total_failed += seg_summary.total_tools_failed
            total_ingested += seg_summary.findings_ingested

        duration = round(perf_counter() - start, 1)
        self._print_summary_table(all_results)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
        )
        self._print_final_line(summary)
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

        if segment_name == "network":
            results_list, total_run, total_skipped, total_failed, total_ingested = (
                self._run_network_segment(auto_approve)
            )
            all_results.extend(results_list)
        else:
            results_list, total_run, total_skipped, total_failed, total_ingested = (
                self._run_repo_segment(SCAN_SEGMENTS[segment_name], auto_approve)
            )
            all_results.extend(results_list)

        duration = round(perf_counter() - start, 1)
        return ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=all_results,
            duration_seconds=duration,
            findings_ingested=total_ingested,
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
        self.console.print(f"\n[bold cyan]Repo Scan:[/bold cyan] {repo.name}")
        self.console.print(f"Languages: {lang_str}")
        self.console.print(f"Tools: {', '.join(ordered_tools)}\n")

        start = perf_counter()
        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = 0

        for tool_name in ordered_tools:
            # ZAP requires base_urls
            if tool_name == "zap" and not repo.base_urls:
                self.console.print(
                    "  [dim]- zap | SKIPPED (no base_urls configured)[/dim]"
                )
                total_skipped += 1
                continue

            tool = self.registry.get_tool(tool_name)
            if tool is None:
                self.console.print(
                    f"  [dim]- {tool_name} | SKIPPED (not registered)[/dim]"
                )
                total_skipped += 1
                continue
            if not tool.check_available():
                self.console.print(
                    f"  [dim]- {tool_name} | SKIPPED (not installed)[/dim]"
                )
                total_skipped += 1
                continue

            self.console.print(f"  [dim][*] Running {tool_name}...[/dim]")
            kwargs = self._repo_tool_kwargs(tool_name, repo, exclude_dirs=exclude_dirs)

            if tool_name == "gitleaks":
                result = self._run_gitleaks_both_scans(tool, kwargs, auto_approve)
            else:
                result = self._run_tool_with_approval(tool, kwargs, auto_approve)

            if result is None:
                self._print_tool_line(tool_name, "SKIPPED", 0, None)
                total_skipped += 1
            else:
                result = self._normalize_success(result)
                results.append(result)
                findings = self._count_findings(result)
                if result.success:
                    total_run += 1
                    self._print_tool_line(
                        tool_name, "pass", findings, result.duration_seconds
                    )
                else:
                    total_failed += 1
                    self._print_tool_line(tool_name, "fail", 0, result.duration_seconds)

        duration = round(perf_counter() - start, 1)
        ingested = self._batch_ingest(results, profile=repo.name)

        self._print_summary_table(results)
        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results,
            duration_seconds=duration,
            findings_ingested=ingested,
        )
        self._print_final_line(summary)
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

        title = (
            f"[bold cyan]Repo Tool Scan:[/bold cyan] {self.project_name} — {tool_name}"
        )
        self.console.print(f"\n{title}")
        self.console.print("─" * 50)

        results_list, total_run, total_skipped, total_failed, total_ingested = (
            self._run_repo_segment([tool_name], auto_approve)
        )

        duration = round(perf_counter() - start, 1)
        self._print_summary_table(results_list)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results_list,
            duration_seconds=duration,
            findings_ingested=total_ingested,
        )
        self._print_final_line(summary)
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

        tool = self.registry.get_tool(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' is not registered.")
        if not tool.check_available():
            raise ValueError(f"Tool '{tool_name}' is not installed.")

        self.console.print(
            f"\n[bold cyan]Repo Tool Scan:[/bold cyan] {repo.name} — {tool_name}"
        )
        self.console.print("─" * 50)

        start = perf_counter()
        kwargs = self._repo_tool_kwargs(tool_name, repo)

        if tool_name == "gitleaks":
            result = self._run_gitleaks_both_scans(tool, kwargs, auto_approve)
        else:
            result = self._run_tool_with_approval(tool, kwargs, auto_approve)

        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = 0

        if result is None:
            self._print_tool_line(tool_name, "SKIPPED", 0, None)
            total_skipped += 1
        else:
            result = self._normalize_success(result)
            results.append(result)
            findings = self._count_findings(result)
            if result.success:
                total_run += 1
                self._print_tool_line(
                    tool_name, "pass", findings, result.duration_seconds
                )
            else:
                total_failed += 1
                self._print_tool_line(tool_name, "fail", 0, result.duration_seconds)

        duration = round(perf_counter() - start, 1)
        ingested = self._batch_ingest(results, profile=repo.name)
        self._print_summary_table(results)

        summary = ScanSummary(
            total_tools_run=total_run,
            total_tools_skipped=total_skipped,
            total_tools_failed=total_failed,
            results=results,
            duration_seconds=duration,
            findings_ingested=ingested,
        )
        self._print_final_line(summary)
        return summary

    def _run_tool_with_approval(
        self,
        tool: ToolWrapper,
        kwargs: dict,
        auto_approve: bool,
    ) -> ToolResult | None:
        """Prompt 'Run <tool>? [y/N]' unless auto_approve is True.

        Returns:
            ToolResult on execution, None if user declines.
        """
        if not auto_approve:
            try:
                answer = input(f"Run {tool.name}? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if answer not in ("y", "yes"):
                return None

        # Extract executor-level kwargs before passing build_command kwargs
        kwargs = dict(kwargs)
        label = kwargs.pop("label", "output")
        cwd = kwargs.pop("cwd", None)
        return self.executor.execute(
            tool, auto_approve=True, label=label, cwd=cwd, **kwargs
        )

    def _run_gitleaks_both_scans(
        self,
        tool: ToolWrapper,
        kwargs: dict,
        auto_approve: bool,
    ) -> ToolResult | None:
        """Run gitleaks dir + git scans, combine, and return one ToolResult.

        Prompts once for approval (if not auto_approve), then runs both scan
        types with auto_approve=True.
        """
        if not auto_approve:
            try:
                answer = input(f"Run {tool.name} (dir + git)? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if answer not in ("y", "yes"):
                return None

        base_kwargs = {k: v for k, v in kwargs.items() if k not in ("label", "cwd")}
        label = kwargs.get("label", "output")
        cwd = kwargs.get("cwd", None)

        dir_result = self.executor.execute(
            tool,
            auto_approve=True,
            label=f"{label}_dir",
            cwd=cwd,
            scan_type="dir",
            **base_kwargs,
        )
        git_result = self.executor.execute(
            tool,
            auto_approve=True,
            label=f"{label}_git",
            cwd=cwd,
            scan_type="git",
            **base_kwargs,
        )

        dir_data = dir_result.parsed_data or {}
        git_data = git_result.parsed_data or {}
        combined_data = combine_gitleaks_results(dir_data, git_data)

        combined_files: dict[str, Path] = {}
        for key, path in dir_result.output_files.items():
            combined_files[f"dir_{key}"] = path
        for key, path in git_result.output_files.items():
            combined_files[f"git_{key}"] = path

        return ToolResult(
            tool_name="gitleaks",
            success=dir_result.success or git_result.success,
            output=(dir_result.output or "") + "\n" + (git_result.output or ""),
            parsed_data=combined_data,
            output_files=combined_files,
            timestamp=dir_result.timestamp,
            duration_seconds=dir_result.duration_seconds + git_result.duration_seconds,
        )

    def _batch_ingest(self, results: list[ToolResult], profile: str) -> int:
        """Ingest all successful ToolResults into RAG after scan completes.

        Uses delete-insert upsert: deletes old findings for tool+profile,
        then inserts fresh ones.

        Returns:
            Total number of documents ingested.
        """
        if self.rag_engine is None:
            return 0

        from core.rag.ingestor import FindingIngestor

        total = 0
        try:
            ingestor = FindingIngestor(self.rag_engine, self.project_name)  # type: ignore[arg-type]
            for result in results:
                if (
                    result.success
                    and result.parsed_data
                    and "error" not in result.parsed_data
                ):
                    try:
                        doc_ids = ingestor.ingest_tool_output(result, profile=profile)
                        total += len(doc_ids)
                    except Exception as exc:
                        logger.error(
                            "Ingestion failed for %s: %s", result.tool_name, exc
                        )
        except Exception as exc:
            logger.error("Batch ingestion setup error: %s", exc)

        return total

    # ------------------------------------------------------------------
    # Private — segment runners
    # ------------------------------------------------------------------

    def _run_network_segment(
        self,
        auto_approve: bool,
    ) -> tuple[list[ToolResult], int, int, int, int]:
        """Run nmap for each configured profile.

        Returns (results, run, skipped, failed, ingested).
        """
        results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0

        profiles = self._config.load_nmap_hosts(self.project_name) or {}
        if not profiles:
            self.console.print(
                "[yellow]No nmap profiles configured"
                " — skipping network segment[/yellow]"
            )
            total_skipped += 1
            return results, total_run, total_skipped, total_failed, total_ingested

        tool = self.registry.get_tool("nmap")
        if tool is None:
            self.console.print("[dim]- nmap | SKIPPED (not registered)[/dim]")
            total_skipped += len(profiles)
            return results, total_run, total_skipped, total_failed, total_ingested

        if not tool.check_available():
            self.console.print("[dim]- nmap | SKIPPED (not installed)[/dim]")
            total_skipped += len(profiles)
            return results, total_run, total_skipped, total_failed, total_ingested

        for profile_name in profiles:
            self.console.print(f"  [dim][*] Running nmap ({profile_name})...[/dim]")
            kwargs = self._nmap_kwargs(profile_name)
            result = self._run_tool_with_approval(tool, kwargs, auto_approve)

            if result is None:
                self._print_tool_line(f"nmap/{profile_name}", "SKIPPED", 0, None)
                total_skipped += 1
            else:
                results.append(result)
                findings = self._count_findings(result)
                if result.success:
                    total_run += 1
                    self._print_tool_line(
                        f"nmap/{profile_name}",
                        "pass",
                        findings,
                        result.duration_seconds,
                    )
                    total_ingested += self._batch_ingest([result], profile=profile_name)
                else:
                    total_failed += 1
                    self._print_tool_line(
                        f"nmap/{profile_name}", "fail", 0, result.duration_seconds
                    )

        return results, total_run, total_skipped, total_failed, total_ingested

    def _run_repo_segment(
        self,
        tool_names: list[str],
        auto_approve: bool,
    ) -> tuple[list[ToolResult], int, int, int, int]:
        """Run a set of tools on every configured repository.

        Returns (results, run, skipped, failed, ingested).
        """
        repos = self._config.load_repositories(self.project_name)
        if not repos:
            self.console.print("[yellow]No repositories configured — skipping[/yellow]")
            return [], 0, len(tool_names), 0, 0

        all_results: list[ToolResult] = []
        total_run = total_skipped = total_failed = total_ingested = 0

        for repo in repos:
            self.console.print(f"  [bold]Repository:[/bold] {repo.name}")
            repo_results: list[ToolResult] = []

            for tool_name in tool_names:
                if tool_name == "zap" and not repo.base_urls:
                    self.console.print("  [dim]- zap | SKIPPED (no base_urls)[/dim]")
                    total_skipped += 1
                    continue

                tool = self.registry.get_tool(tool_name)
                if tool is None:
                    self.console.print(
                        f"  [dim]- {tool_name} | SKIPPED (not registered)[/dim]"
                    )
                    total_skipped += 1
                    continue
                if not tool.check_available():
                    self.console.print(
                        f"  [dim]- {tool_name} | SKIPPED (not installed)[/dim]"
                    )
                    total_skipped += 1
                    continue

                self.console.print(
                    f"  [dim][*] Running {tool_name} ({repo.name})...[/dim]"
                )
                kwargs = self._repo_tool_kwargs(tool_name, repo)

                if tool_name == "gitleaks":
                    result = self._run_gitleaks_both_scans(tool, kwargs, auto_approve)
                else:
                    result = self._run_tool_with_approval(tool, kwargs, auto_approve)

                if result is None:
                    self._print_tool_line(
                        f"{tool_name}/{repo.name}", "SKIPPED", 0, None
                    )
                    total_skipped += 1
                else:
                    result = self._normalize_success(result)
                    repo_results.append(result)
                    findings = self._count_findings(result)
                    if result.success:
                        total_run += 1
                        self._print_tool_line(
                            f"{tool_name}/{repo.name}",
                            "pass",
                            findings,
                            result.duration_seconds,
                        )
                    else:
                        total_failed += 1
                        self._print_tool_line(
                            f"{tool_name}/{repo.name}",
                            "fail",
                            0,
                            result.duration_seconds,
                        )

            all_results.extend(repo_results)
            total_ingested += self._batch_ingest(repo_results, profile=repo.name)

        return all_results, total_run, total_skipped, total_failed, total_ingested

    # ------------------------------------------------------------------
    # Private — kwargs builders
    # ------------------------------------------------------------------

    def _nmap_kwargs(self, profile_name: str) -> dict:
        return {
            "label": profile_name,
            "profile": profile_name,
            "project_name": self.project_name,
            "base_path": str(self.executor.base_path),
        }

    def _repo_tool_kwargs(
        self,
        tool_name: str,
        repo,
        exclude_dirs: list[str] | None = None,
    ) -> dict:
        repo_path = self.registry.get_repo_path(tool_name, repo)
        kwargs: dict = {"label": repo.name, "repo_path": repo_path}

        if tool_name in ("npm-audit", "composer-audit"):
            # Docker wrappers handle working directory internally via -w;
            # only set cwd for local tools.
            tool_config = self.registry.get_tool_config(tool_name)
            if tool_config is None or tool_config.location == "local":
                kwargs["cwd"] = repo_path

        if tool_name == "zap" and repo.base_urls:
            endpoint_cfg = self._config.load_endpoint_config(
                self.project_name, repo.name
            )
            endpoints_dict = endpoint_cfg.endpoints if endpoint_cfg else {}
            kwargs["base_url"] = repo.base_urls[0]
            kwargs["endpoints"] = endpoints_dict
            # output_file only applies to local ZAP;
            # docker ZAP writes inside the container
            tool_config = self.registry.get_tool_config(tool_name)
            if tool_config is None or tool_config.location == "local":
                output_dir = (
                    self.executor.base_path
                    / "projects"
                    / self.project_name
                    / "tool_outputs"
                    / "zap"
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                kwargs["output_file"] = str(
                    output_dir / f"{repo.name}_{ts}_report.json"
                )

        return kwargs

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

    @staticmethod
    def _count_findings(result: ToolResult) -> int:
        if not result.parsed_data:
            return 0
        pd = result.parsed_data
        summary = pd.get("summary", {})
        if "hosts" in pd:
            return len(pd["hosts"])
        if "total_findings" in summary:
            return summary["total_findings"]
        if "findings" in pd:
            return len(pd["findings"])
        if "total_vulnerabilities" in summary:
            return summary["total_vulnerabilities"]
        if "vulnerabilities" in pd:
            return len(pd["vulnerabilities"])
        if "total_secrets" in summary:
            return summary["total_secrets"]
        if "secrets" in pd:
            return len(pd["secrets"])
        if "total_alerts" in summary:
            return summary["total_alerts"]
        if "alerts" in pd:
            return len(pd["alerts"])
        return 0

    # ------------------------------------------------------------------
    # Private — Rich display helpers
    # ------------------------------------------------------------------

    def _print_tool_line(
        self,
        tool_name: str,
        status: str,
        findings: int,
        duration: float | None,
    ) -> None:
        icons = {
            "pass": "[green]✓[/green]",
            "fail": "[red]✗[/red]",
            "SKIPPED": "[dim]-[/dim]",
        }
        icon = icons.get(status, status)
        findings_str = (
            f"{findings} findings"
            if status == "pass"
            else ("-" if status == "SKIPPED" else "FAILED")
        )
        dur_str = f"{duration:.1f}s" if duration is not None else "-"
        self.console.print(
            f"  {icon} [cyan]{tool_name:<22}[/cyan] | {findings_str:<14} | {dur_str}"
        )

    def _print_summary_table(self, results: list[ToolResult]) -> None:
        if not results:
            return
        table = Table(title=None, show_header=True, header_style="bold")
        table.add_column("Tool", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Findings", style="white")
        table.add_column("Duration", style="white")
        for r in results:
            status = "pass" if r.success else "fail"
            findings = str(self._count_findings(r))
            dur = f"{r.duration_seconds:.1f}s"
            table.add_row(r.tool_name, status, findings, dur)
        self.console.print()
        self.console.print(table)

    def _print_final_line(self, summary: ScanSummary) -> None:
        self.console.print(
            f"\n[bold]Scan complete:[/bold] "
            f"[green]{summary.total_tools_run} passed[/green], "
            f"[red]{summary.total_tools_failed} failed[/red], "
            f"[dim]{summary.total_tools_skipped} skipped[/dim] | "
            f"{summary.findings_ingested} findings ingested | "
            f"{summary.duration_seconds:.1f}s total"
        )
