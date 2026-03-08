"""Scan execution commands for the tally REPL."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.tools.base import ToolResult
from core.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from core.tools.parsers.gitleaks_parser import combine_gitleaks_results
from core.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.repl.interface import REPL


def _ingest_result(repl: REPL, result: ToolResult, profile: str | None = None) -> int:
    """Ingest a ToolResult into the project's RAG store. Returns document count."""
    from core.rag import FindingIngestor, RAGEngine

    try:
        rag_engine = RAGEngine(
            project_name=repl.active_project,
            base_path=repl.base_path,
        )
        ingestor = FindingIngestor(rag_engine, repl.active_project)
        return ingestor.ingest_tool_output(result, profile=profile)
    except (RuntimeError, ValueError) as exc:
        repl.console.print(f"[red]Ingestion error:[/red] {exc}")
        return 0


class ScanCommands:
    """Handlers for tool scan execution commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_scan(self, _cmd: str, args: list[str]) -> None:
        """scan [<tool>] | scan repo [<tool>]  — run tool scans."""
        auto_approve, args = self._parse_bool_flag(args, "-y", "--yes")
        segment_name, args = self._parse_value_flag(args, "-s", "--segment")

        if args:
            first = args[0].lower()

            if first == "repo":
                # scan repo [<tool>]
                repo_args = args[1:]
                if repo_args and not repo_args[0].startswith("-"):
                    self._cmd_scan_repo_tool(repo_args[0].lower(), auto_approve)
                else:
                    self._cmd_scan_repo(repo_args, auto_approve)
                return

            # scan <tool>
            tool_name = first
            remaining = args[1:]
            timeout, remaining = self._parse_timeout_arg(remaining)
            if tool_name == "nmap":
                self._cmd_scan_nmap(remaining, timeout)
            elif tool_name == "semgrep":
                self._cmd_scan_semgrep(remaining, timeout)
            elif tool_name in ("osv-scanner", "osv"):
                self._cmd_scan_osv(remaining, timeout)
            elif tool_name == "pip-audit":
                self._cmd_scan_pip_audit(remaining, timeout)
            elif tool_name == "npm-audit":
                self._cmd_scan_npm_audit(remaining, timeout)
            elif tool_name == "composer-audit":
                self._cmd_scan_composer_audit(remaining, timeout)
            elif tool_name == "gitleaks":
                self._cmd_scan_gitleaks(remaining, timeout)
            elif tool_name == "zap":
                self._cmd_scan_zap(remaining, timeout)
            else:
                known = tool_registry.list_tool_names()
                self.repl.console.print(
                    f"[red]Unknown tool:[/red] {tool_name}\n"
                    f"Configured tools: {', '.join(sorted(known))}"
                )
            return

        # scan (no args) → full project scan or segment scan
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        from core.tools.orchestrator import SCAN_SEGMENTS

        orchestrator = self._make_orchestrator()
        if orchestrator is None:
            return

        if segment_name is not None:
            valid_segments = list(SCAN_SEGMENTS)
            if segment_name not in valid_segments:
                self.repl.console.print(
                    f"[red]Invalid segment:[/red] {segment_name!r}. "
                    f"Valid: {', '.join(valid_segments)}"
                )
                return
            orchestrator.run_segment(segment_name, auto_approve=auto_approve)
        else:
            orchestrator.run_full_scan(auto_approve=auto_approve)

    def cmd_run(self, _cmd: str, args: list[str]) -> None:
        """run <tool> [--timeout <seconds>] [args...]  — execute a tool with raw
        arguments.
        """
        if not args:
            self.repl.console.print(
                "[red]Usage:[/red] run <tool> [--timeout <seconds>] [args...]"
            )
            return

        tool_name = args[0].lower()
        remaining = args[1:]
        timeout, remaining = self._parse_timeout_arg(remaining)

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool(tool_name)
        if tool is None:
            self.repl.console.print(f"[red]Tool not found:[/red] {tool_name}")
            return

        if not tool.check_available():
            self.repl.console.print(
                f"[red]Tool not installed:[/red] {tool_name}. "
                f"Install with: apt install {tool_name}"
            )
            return

        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        result = executor.execute(
            tool,
            timeout=timeout,
            label="manual",
            args=" ".join(remaining),
            hosts=[],
        )

        self._print_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        if self._ask_ingest():
            count = _ingest_result(self.repl, result)
            if count > 0:
                self.repl.console.print(f"[green]✓ Ingested {count} findings[/green]")
            else:
                self.repl.console.print("[yellow]No findings to ingest.[/yellow]")

    # todo: These all need to be their own modules, this is getting ridiculous.
    # ------------------------------------------------------------------
    # Private — nmap scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_nmap(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("nmap")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] nmap")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] nmap. Install with: apt install nmap"
            )
            return

        profile = remaining[0] if remaining else None

        if profile:
            self.repl.console.print(f"Running nmap: {profile}...")
            self._run_nmap_profile(profile, timeout)
        else:
            profiles = self.repl.config.load_nmap_hosts(self.repl.active_project)
            if not profiles:
                self.repl.console.print(
                    "[yellow]No nmap profiles configured for this project.[/yellow]"
                )
                return

            profile_names = list(profiles.keys())
            self.repl.console.print("No profile specified. Running all profiles...\n")
            for i, name in enumerate(profile_names, 1):
                self.repl.console.print(
                    f"[{i}/{len(profile_names)}] Running nmap: {name}..."
                )
                self._run_nmap_profile(name, timeout)

            self.repl.console.print("\nAll scans complete.")

    def _run_nmap_profile(self, profile_name: str, timeout: int) -> None:
        result = self._execute_nmap_scan(profile_name, timeout=timeout)
        self._print_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=profile_name)
            if count > 0:
                self.repl.console.print(f"[green]✓ Ingested {count} findings[/green]")
            else:
                self.repl.console.print("[yellow]No findings to ingest.[/yellow]")

    def _execute_nmap_scan(
        self,
        profile_name: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("nmap")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=profile_name,
            profile=profile_name,
            project_name=self.repl.active_project,
            base_path=self.repl.base_path,
        )

    # ------------------------------------------------------------------
    # Private — semgrep scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_semgrep(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("semgrep")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] semgrep")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] semgrep. "
                "Install with: pip install semgrep"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        self.repl.console.print(f"Running semgrep: {repo.name}...")
        repo_path = tool_registry.get_repo_path("semgrep", repo)
        result = self._execute_semgrep_scan(repo.name, repo_path, timeout=timeout)
        self._print_semgrep_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        # semgrep exits with code 1 when findings are present — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f"[green]✓ Ingested {count} findings[/green]")
            else:
                self.repl.console.print("[yellow]No findings to ingest.[/yellow]")

    def _execute_semgrep_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("semgrep")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — osv-scanner scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_osv(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("osv-scanner")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] osv-scanner")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] osv-scanner. "
                "Install with: "
                "go install github.com/google/osv-scanner/cmd/osv-scanner@latest"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        self.repl.console.print(f"Running osv-scanner: {repo.name}...")
        repo_path = tool_registry.get_repo_path("osv-scanner", repo)
        result = self._execute_osv_scan(repo.name, repo_path, timeout=timeout)
        self._print_osv_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        # osv-scanner exits with code 1 when vulnerabilities are present —
        # not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(
                    f"[green]✓ Ingested {count} vulnerabilities[/green]"
                )
            else:
                self.repl.console.print(
                    "[yellow]No vulnerabilities to ingest.[/yellow]"
                )

    def _execute_osv_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("osv-scanner")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    def _print_osv_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_osv(result)
            self.repl.console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self.repl.console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_osv(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_vulnerabilities", 0)
        by_sev = summary.get("by_severity", {})
        parts = [
            f"{by_sev[s]} {s}"
            for s in ("critical", "high", "medium", "low")
            if by_sev.get(s)
        ]
        sev_str = ", ".join(parts) if parts else "none"
        return f"{total} vulnerabilities ({sev_str})"

    # ------------------------------------------------------------------
    # Private — scan repo (language-aware multi-tool SCA on a single repo)
    # ------------------------------------------------------------------

    def _cmd_scan_repo(self, args: list[str], auto_approve: bool = False) -> None:
        """scan repo [--exclude <dirs>] [--severity <level>] [--export <file>]"""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        exclude_str, args = self._parse_value_flag(args, "--exclude")
        severity, args = self._parse_value_flag(args, "--severity")
        export_path, args = self._parse_value_flag(args, "--export")
        _, args = self._parse_timeout_arg(args)  # consume --timeout if present

        if severity and severity not in ("critical", "high", "medium", "low"):
            self.repl.console.print(
                f"[red]Invalid severity:[/red] {severity!r}. "
                "Valid: critical, high, medium, low"
            )
            return

        exclude_dirs = (
            [d.strip() for d in exclude_str.split(",")] if exclude_str else None
        )

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        # Interactive repo selection
        if len(repos) == 1:
            repo_name = repos[0].name
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo_name = repos[idx].name
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        orchestrator = self._make_orchestrator()
        if orchestrator is None:
            return

        try:
            summary = orchestrator.run_repo_scan(
                repo_name=repo_name,
                auto_approve=auto_approve,
                exclude_dirs=exclude_dirs,
                severity_filter=severity,
            )
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        if export_path:
            self._export_summary(summary, export_path)

    # ------------------------------------------------------------------
    # Private — scan repo <tool> (single tool against all repositories)
    # ------------------------------------------------------------------

    def _cmd_scan_repo_tool(self, tool_name: str, auto_approve: bool = False) -> None:
        """scan repo <tool> — run a single tool against all configured repositories."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        known_tools = tool_registry.list_tool_names()
        if tool_name not in known_tools:
            self.repl.console.print(
                f"[red]Unknown tool:[/red] {tool_name}\n"
                f"Configured tools: {', '.join(sorted(known_tools))}"
            )
            return

        if tool_name == "nmap":
            self.repl.console.print(
                "[red]Error:[/red] nmap is a network tool and cannot be run with "
                "'scan repo'. Use 'scan nmap' instead."
            )
            return

        orchestrator = self._make_orchestrator()
        if orchestrator is None:
            return

        try:
            orchestrator.run_tool_on_all_repos(tool_name, auto_approve=auto_approve)
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")

    # ------------------------------------------------------------------
    # Private — pip-audit scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_pip_audit(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("pip-audit")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] pip-audit")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] pip-audit. "
                "Install with: pip install pip-audit"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        self.repl.console.print(f"Running pip-audit: {repo.name}...")
        repo_path = tool_registry.get_repo_path("pip-audit", repo)
        result = self._execute_pip_audit_scan(repo.name, repo_path, timeout=timeout)
        self._print_sca_result(result, "pip-audit")

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        # pip-audit exits with code 1 when vulnerabilities are present —
        # not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(
                    f"[green]✓ Ingested {count} vulnerabilities[/green]"
                )
            else:
                self.repl.console.print(
                    "[yellow]No vulnerabilities to ingest.[/yellow]"
                )

    def _execute_pip_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("pip-audit")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — npm-audit scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_npm_audit(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("npm-audit")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] npm-audit")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] npm-audit (requires npm). "
                "Install with: apt install nodejs npm"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        self.repl.console.print(f"Running npm-audit: {repo.name}...")
        repo_path = tool_registry.get_repo_path("npm-audit", repo)
        result = self._execute_npm_audit_scan(repo.name, repo_path, timeout=timeout)
        self._print_sca_result(result, "npm-audit")

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        # npm audit exits with code 1 when vulnerabilities are present —
        # not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(
                    f"[green]✓ Ingested {count} vulnerabilities[/green]"
                )
            else:
                self.repl.console.print(
                    "[yellow]No vulnerabilities to ingest.[/yellow]"
                )

    def _execute_npm_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("npm-audit")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        # Docker wrappers handle cwd via -w internally; only set cwd for local tools.
        config = tool_registry.get_tool_config("npm-audit")
        cwd = repo_path if (config is None or config.location == "local") else None
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            cwd=cwd,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — composer-audit scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_composer_audit(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("composer-audit")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] composer-audit")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] composer-audit (requires composer). "
                "Install with: apt install composer"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        self.repl.console.print(f"Running composer-audit: {repo.name}...")
        repo_path = tool_registry.get_repo_path("composer-audit", repo)
        result = self._execute_composer_audit_scan(
            repo.name, repo_path, timeout=timeout
        )
        self._print_sca_result(result, "composer-audit")

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        # composer audit exits with code 1 when vulnerabilities are present —
        # not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(
                    f"[green]✓ Ingested {count} vulnerabilities[/green]"
                )
            else:
                self.repl.console.print(
                    "[yellow]No vulnerabilities to ingest.[/yellow]"
                )

    def _execute_composer_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("composer-audit")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        # Docker wrappers handle cwd via -w internally; only set cwd for local tools.
        config = tool_registry.get_tool_config("composer-audit")
        cwd = repo_path if (config is None or config.location == "local") else None
        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            cwd=cwd,
            repo_path=repo_path,
        )

    # ------------------------------------------------------------------
    # Private — gitleaks scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_gitleaks(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("gitleaks")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] gitleaks")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] gitleaks. "
                "Install with: apt install gitleaks"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        self.repl.console.print(f"Running gitleaks: {repo.name}...")
        repo_path = tool_registry.get_repo_path("gitleaks", repo)
        result = self._execute_gitleaks_both_scans(
            repo.name, repo_path, timeout=timeout
        )
        self._print_gitleaks_result(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        # gitleaks exits with code 1 when secrets are found — not a true failure
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True

        if self._ask_ingest():
            count = _ingest_result(self.repl, result, profile=repo.name)
            if count > 0:
                self.repl.console.print(f"[green]✓ Ingested {count} secrets[/green]")
            else:
                self.repl.console.print("[yellow]No secrets to ingest.[/yellow]")

    def _execute_gitleaks_both_scans(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        """Run gitleaks dir + git scans and return a single combined ToolResult.

        Prompts once for approval (unless auto_approve), then runs both scan
        types with auto_approve=True so the executor does not prompt twice.
        """
        tool = tool_registry.get_tool("gitleaks")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )

        if not auto_approve:
            try:
                answer = input(f"Run {tool.name} (dir + git)? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return ToolResult(
                    tool_name="gitleaks",
                    success=False,
                    output="Execution denied by user.",
                    parsed_data=None,
                    output_files={},
                    timestamp=ToolResult.now_iso(),
                    duration_seconds=0.0,
                )
            if answer not in ("y", "yes"):
                return ToolResult(
                    tool_name="gitleaks",
                    success=False,
                    output="Execution denied by user.",
                    parsed_data=None,
                    output_files={},
                    timestamp=ToolResult.now_iso(),
                    duration_seconds=0.0,
                )

        dir_result = executor.execute(
            tool,
            auto_approve=True,
            timeout=timeout,
            label=f"{repo_name}_dir",
            repo_path=repo_path,
            scan_type="dir",
        )
        git_result = executor.execute(
            tool,
            auto_approve=True,
            timeout=timeout,
            label=f"{repo_name}_git",
            repo_path=repo_path,
            scan_type="git",
        )

        dir_data = dir_result.parsed_data or {}
        git_data = git_result.parsed_data or {}
        combined_data = combine_gitleaks_results(dir_data, git_data)

        # Write combined JSON to tool_outputs/gitleaks/
        from datetime import datetime

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "tool_outputs"
            / "gitleaks"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        combined_path = output_dir / f"{repo_name}_{ts}_combined.json"
        combined_path.write_text(json.dumps(combined_data, indent=2), encoding="utf-8")

        combined_files: dict[str, Path] = {}
        for key, path in dir_result.output_files.items():
            combined_files[f"dir_{key}"] = path
        for key, path in git_result.output_files.items():
            combined_files[f"git_{key}"] = path
        combined_files["combined"] = combined_path

        return ToolResult(
            tool_name="gitleaks",
            success=dir_result.success or git_result.success,
            output=(dir_result.output or "") + "\n" + (git_result.output or ""),
            parsed_data=combined_data,
            output_files=combined_files,
            timestamp=dir_result.timestamp,
            duration_seconds=dir_result.duration_seconds + git_result.duration_seconds,
        )

    def _execute_gitleaks_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        """Backward-compatible single-scan entry point; delegates to dual-scan."""
        return self._execute_gitleaks_both_scans(
            repo_name,
            repo_path,
            auto_approve=auto_approve,
            timeout=timeout,
        )

    def _print_gitleaks_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            data = result.parsed_data or {}
            total = data.get("summary", {}).get("total_secrets", 0)
            if total > 0:
                self.repl.console.print(
                    "[yellow]⚠  WARNING: Secrets detected![/yellow]"
                )
            summary = self._summarize_gitleaks(result)
            self.repl.console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self.repl.console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_gitleaks(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_secrets", 0)
        if total == 0:
            return "0 secrets found (clean)"
        files_count = summary.get("files_with_secrets", 0)
        by_rule = summary.get("by_rule", {})
        rule_str = ", ".join(f"{count} {rule}" for rule, count in by_rule.items())
        return f"{total} secrets in {files_count} file(s) ({rule_str})"

    # ------------------------------------------------------------------
    # Private — ZAP scan flow
    # ------------------------------------------------------------------

    def _cmd_scan_zap(self, remaining: list[str], timeout: int) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        tool = tool_registry.get_tool("zap")
        if tool is None:
            self.repl.console.print("[red]Tool not found:[/red] zap")
            return

        if not tool.check_available():
            self.repl.console.print(
                "[red]Tool not installed:[/red] zap. "
                "Install with: apt install zaproxy  (or download from zaproxy.org)"
            )
            return

        repos = self.repl.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print(
                "[yellow]No repositories configured. "
                "Use 'repo add' to add one.[/yellow]"
            )
            return

        if len(repos) == 1:
            repo = repos[0]
        else:
            self.repl.console.print("\nSelect repository:")
            for i, r in enumerate(repos, 1):
                self.repl.console.print(f"  {i}. {r.name} ({r.path})")
            try:
                raw = input("\nChoice: ").strip()
                idx = int(raw) - 1
                if not (0 <= idx < len(repos)):
                    self.repl.console.print("[red]Invalid choice.[/red]")
                    return
                repo = repos[idx]
            except (ValueError, EOFError, KeyboardInterrupt):
                self.repl.console.print("[red]Invalid choice.[/red]")
                return

        if not repo.base_urls:
            self.repl.console.print(
                "[yellow]No base_urls configured for this repository.[/yellow]\n"
                "Add base_urls to the repository config (e.g. 'http://localhost:8080')."
            )
            return

        endpoint_cfg = self.repl.config.load_endpoint_config(
            self.repl.active_project, repo.name
        )
        if endpoint_cfg is None:
            self.repl.console.print(
                f"[yellow]No endpoint config found for {repo.name!r}.[/yellow]\n"
                f"Create one at: projects/{self.repl.active_project}"
                f"/config/endpoints/{repo.name}.json\n"
                "ZAP will still run using quick-scan mode (spider from base_url)."
            )
        endpoints_dict: dict[str, list[str]] = (
            endpoint_cfg.endpoints if endpoint_cfg else {}
        )

        for base_url in repo.base_urls:
            self.repl.console.print(
                f"Running ZAP: {repo.name} → [cyan]{base_url}[/cyan]..."
            )
            result = self._execute_zap_scan(
                repo.name, base_url, endpoints_dict, timeout=timeout
            )
            self._print_zap_result(result)

            if result.output_files:
                for path in result.output_files.values():
                    self.repl.console.print(f"Output saved to: {path}")

            # ZAP exits non-zero when alerts are found — not a true failure
            if result.parsed_data and "error" not in result.parsed_data:
                result.success = True

            if self._ask_ingest():
                count = _ingest_result(self.repl, result, profile=repo.name)
                if count > 0:
                    self.repl.console.print(f"[green]✓ Ingested {count} alerts[/green]")
                else:
                    self.repl.console.print("[yellow]No alerts to ingest.[/yellow]")

    def _execute_zap_scan(
        self,
        repo_name: str,
        base_url: str,
        endpoints: dict[str, list[str]],
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        tool = tool_registry.get_tool("zap")
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        # Compute report path inside the project's tool_outputs/zap directory
        output_dir = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "tool_outputs"
            / "zap"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_file = str(output_dir / f"{repo_name}_{ts}_report.json")

        return executor.execute(
            tool,
            auto_approve=auto_approve,
            timeout=timeout,
            label=repo_name,
            base_url=base_url,
            endpoints=endpoints,
            output_file=output_file,
        )

    def _print_zap_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_zap(result)
            self.repl.console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self.repl.console.print(f"[red]✗ Scan failed:[/red] {result.output[:200]}")

    @staticmethod
    def _summarize_zap(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_alerts", 0)
        by_risk = summary.get("by_risk", {})
        parts = [
            f"{by_risk[r]} {r}"
            for r in ("high", "medium", "low", "informational")
            if by_risk.get(r)
        ]
        risk_str = ", ".join(parts) if parts else "none"
        urls = summary.get("urls_scanned", 0)
        return f"{total} alerts ({risk_str}), {urls} URLs scanned"

    # ------------------------------------------------------------------
    # Private — shared SCA result helpers
    # ------------------------------------------------------------------

    def _print_sca_result(self, result: ToolResult, tool_name: str) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_sca(result)
            self.repl.console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self.repl.console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_sca(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_vulnerabilities", 0)
        by_sev = summary.get("by_severity", {})
        parts = [
            f"{by_sev[s]} {s}"
            for s in ("critical", "high", "medium", "low")
            if by_sev.get(s)
        ]
        sev_str = ", ".join(parts) if parts else "none"
        return f"{total} vulnerabilities ({sev_str})"

    @staticmethod
    def _select_repo_tools(
        languages: list[str],
        base_urls: list[str] | None = None,
    ) -> list[str]:
        """Return tool names for a full repository scan.

        osv-scanner is always included as a baseline multi-ecosystem scanner.
        gitleaks is always included for secrets detection.
        Language-specific tools are added based on detected languages.
        zap is included when the repository has base_urls configured.
        """
        tools = ["osv-scanner"]
        lowered = {lang.lower() for lang in languages}
        if "python" in lowered:
            tools.append("pip-audit")
        if lowered & {"javascript", "typescript", "javascript/typescript", "node"}:
            tools.append("npm-audit")
        if "php" in lowered:
            tools.append("composer-audit")
        tools.append("gitleaks")
        if base_urls:
            tools.append("zap")
        return tools

    def _print_semgrep_result(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_semgrep(result)
            self.repl.console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self.repl.console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_semgrep(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_findings", 0)
        by_sev = summary.get("by_severity", {})
        parts = [
            f"{by_sev[s]} {s}"
            for s in ("high", "medium", "low")
            if by_sev.get(s)
        ]
        sev_str = ", ".join(parts) if parts else "none"
        return f"{total} findings ({sev_str})"

    # ------------------------------------------------------------------
    # Private — UI helpers
    # ------------------------------------------------------------------

    def _print_result(self, result: ToolResult) -> None:
        if result.success:
            summary = self._summarize_result(result)
            self.repl.console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self.repl.console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    def _ask_ingest(self) -> bool:
        try:
            answer = input("Ingest findings? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ("y", "yes")

    @staticmethod
    def _summarize_result(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        hosts = result.parsed_data.get("hosts", [])
        up_hosts = [h for h in hosts if h.get("state") == "up"]
        open_ports = sum(
            len([p for p in h.get("ports", []) if p.get("state") == "open"])
            for h in up_hosts
        )
        return f"{len(up_hosts)} hosts up, {open_ports} open ports"

    @staticmethod
    def _parse_timeout_arg(
        args: list[str],
    ) -> tuple[int, list[str]]:
        """Extract --timeout <seconds> from args. Returns (timeout, remaining_args)."""
        for i, token in enumerate(args):
            if token == "--timeout" and i + 1 < len(args):
                raw = args[i + 1]
                try:
                    seconds = int(raw)
                    if seconds <= 0:
                        raise ValueError
                except ValueError:
                    raise ValueError(
                        f"--timeout requires a positive integer, got {raw!r}"
                    )
                remaining = args[:i] + args[i + 2 :]
                return seconds, remaining
        return DEFAULT_TIMEOUT, args

    @staticmethod
    def _parse_bool_flag(args: list[str], *flags: str) -> tuple[bool, list[str]]:
        """Extract a boolean flag. Returns (found, remaining_args)."""
        for flag in flags:
            if flag in args:
                remaining = [a for a in args if a != flag]
                return True, remaining
        return False, args

    @staticmethod
    def _parse_value_flag(args: list[str], *flags: str) -> tuple[str | None, list[str]]:
        """Extract a value flag (e.g. --severity high).

        Returns (value_or_None, remaining_args).
        """
        for i, token in enumerate(args):
            if token in flags and i + 1 < len(args):
                value = args[i + 1]
                remaining = args[:i] + args[i + 2 :]
                return value, remaining
        return None, args

    # ------------------------------------------------------------------
    # Private — orchestrator factory and export
    # ------------------------------------------------------------------

    def _make_orchestrator(self):
        """Create a ScanOrchestrator for the active project. Returns None on failure."""
        from core.tools.executor import ToolExecutor
        from core.tools.orchestrator import ScanOrchestrator

        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )

        rag_engine = None
        try:
            from core.rag.engine import RAGEngine

            rag_engine = RAGEngine(
                project_name=self.repl.active_project,
                base_path=self.repl.base_path,
            )
        except (RuntimeError, ValueError) as exc:
            self.repl.console.print(
                f"[yellow]RAG unavailable (ingestion disabled):[/yellow] {exc}"
            )

        return ScanOrchestrator(
            project=self.repl.active_project,
            tool_registry=tool_registry,
            tool_executor=executor,
            rag_engine=rag_engine,
        )

    def _export_summary(self, summary, export_path: str) -> None:
        """Export ScanSummary results to a JSON file."""
        import json

        try:
            data = {
                "total_tools_run": summary.total_tools_run,
                "total_tools_skipped": summary.total_tools_skipped,
                "total_tools_failed": summary.total_tools_failed,
                "duration_seconds": summary.duration_seconds,
                "findings_ingested": summary.findings_ingested,
                "results": [
                    {
                        "tool_name": r.tool_name,
                        "success": r.success,
                        "duration_seconds": r.duration_seconds,
                        "timestamp": r.timestamp,
                        "findings": r.parsed_data,
                    }
                    for r in summary.results
                ],
            }
            Path(export_path).write_text(json.dumps(data, indent=2, default=str))
            self.repl.console.print(f"[green]✓ Exported to:[/green] {export_path}")
        except Exception as exc:
            self.repl.console.print(f"[red]Export failed:[/red] {exc}")
