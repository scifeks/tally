"""Scan execution commands for the tally REPL."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.tools.base import ToolResult
from core.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from core.tools.factory import ToolWrapperFactory
from core.tools.parsers.gitleaks_parser import combine_gitleaks_results
from core.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.repl.interface import REPL


def _enrich_results(
    repl: REPL,
    doc_ids: list[str],
    sqlite_store: object = None,
    run_id: int | None = None,
) -> None:
    """Run enrichment pipeline on freshly ingested document IDs."""
    from core.rag import EnrichmentPipeline, RAGEngine

    assert repl.active_project is not None
    try:
        rag_engine = RAGEngine(
            project_name=repl.active_project,
            base_path=repl.base_path,
        )
        pipeline = EnrichmentPipeline(
            rag_engine,
            console=repl.console,
            sqlite_store=sqlite_store,  # type: ignore[arg-type]
            run_id=run_id,
        )
        pipeline.enrich(doc_ids)
    except (RuntimeError, ValueError) as exc:
        repl.console.print(f"[red]Enrichment error:[/red] {exc}")


def _ingest_result(
    repl: REPL, result: ToolResult, profile: str | None = None
) -> list[str]:
    """Ingest a ToolResult into the project's RAG store. Returns list of doc IDs."""
    from core.rag import FindingIngestor, RAGEngine

    assert repl.active_project is not None
    try:
        rag_engine = RAGEngine(
            project_name=repl.active_project,
            base_path=repl.base_path,
        )
        ingestor = FindingIngestor(rag_engine, repl.active_project)
        return ingestor.ingest_tool_output(result, profile=profile)
    except (RuntimeError, ValueError) as exc:
        repl.console.print(f"[red]Ingestion error:[/red] {exc}")
        return []


class ScanCommands:
    """Handlers for tool scan execution commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_scan(self, _cmd: str, args: list[str]) -> None:
        """scan [--repo=<repo>] [--tool=<tool,...>] [--type=<type,...>]"""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        from core.tools.registry import discover_tools

        discover_tools(self.repl.base_path, project_name=self.repl.active_project)
        try:
            self._cmd_scan_inner(args)
        finally:
            discover_tools(self.repl.base_path)

    def _cmd_scan_inner(self, args: list[str]) -> None:
        """Inner scan logic — runs after registry is refreshed."""
        from core.tools.constants import DOMAINS, TOOL_DOMAIN_MAP

        auto_approve = "--yes" in args
        args = [a for a in args if a != "--yes"]

        repo_val: str | None = None
        tool_val: str | None = None
        type_val: str | None = None
        unrecognized: list[str] = []

        for arg in args:
            if arg.startswith("--repo="):
                repo_val = arg[7:]
            elif arg.startswith("--tool="):
                tool_val = arg[7:]
            elif arg.startswith("--type="):
                type_val = arg[7:]
            else:
                unrecognized.append(arg)

        if unrecognized:
            self.repl.console.print(
                f"[red]Unrecognized argument(s):[/red] {', '.join(unrecognized)}\n"
                "Usage: scan [--repo=<repo>] [--tool=<tool,...>]"
                " [--type=<type,...>] [--yes]"
            )
            return

        assert self.repl.active_project is not None

        # Validate --repo
        repo_name: str | None = None
        if repo_val is not None:
            repos = self.repl.config.load_repositories(self.repl.active_project)
            match = next((r for r in repos if r.name.lower() == repo_val.lower()), None)
            if match is None:
                names = sorted(r.name for r in repos)
                self.repl.console.print(
                    f"[red]Unknown repository:[/red] {repo_val!r}\n"
                    f"Configured repos: {', '.join(names) or 'none'}"
                )
                return
            repo_name = match.name

        # Validate --tool
        requested_tools: list[str] | None = None
        if tool_val is not None:
            requested_tools = [t.strip() for t in tool_val.split(",") if t.strip()]
            known = set(tool_registry.list_tool_names())
            invalid = [t for t in requested_tools if t not in known]
            if invalid:
                self.repl.console.print(
                    f"[red]Unknown tool(s):[/red] {', '.join(invalid)}\n"
                    f"Configured tools: {', '.join(sorted(known))}"
                )
                return

        # Validate --type
        requested_types: list[str] | None = None
        if type_val is not None:
            requested_types = [t.strip() for t in type_val.split(",") if t.strip()]
            invalid_t = [t for t in requested_types if t not in DOMAINS]
            if invalid_t:
                self.repl.console.print(
                    f"[red]Unknown type(s):[/red] {', '.join(invalid_t)}\n"
                    f"Valid types: {', '.join(sorted(DOMAINS))}"
                )
                return

        # Compute effective tool list (intersection of --tool and --type filters)
        effective_tools: list[str] | None = None
        if requested_tools is not None or requested_types is not None:
            all_configured = list(tool_registry.list_tool_names())
            candidates = (
                list(requested_tools) if requested_tools is not None else all_configured
            )
            if requested_types is not None:
                candidates = [
                    t for t in candidates if TOOL_DOMAIN_MAP.get(t) in requested_types
                ]
            effective_tools = candidates

        _sqlite_store, run_id = self._create_sqlite_run(args)
        orchestrator = self._make_orchestrator(run_id=run_id)
        if orchestrator is None:
            return

        if auto_approve:
            orchestrator._auto_approve = True

        try:
            if repo_name is not None:
                if effective_tools is not None:
                    # Network tools (nmap) cannot be scoped to a single repo
                    net = [
                        t
                        for t in effective_tools
                        if TOOL_DOMAIN_MAP.get(t) == "network"
                    ]
                    if net:
                        self.repl.console.print(
                            f"[red]Error:[/red] Network tool(s) cannot be scoped"
                            f" to a repository: {', '.join(net)}\n"
                            "Omit --repo to run network tools."
                        )
                        return
                    for tool_name in effective_tools:
                        orchestrator.run_tool_on_repo(tool_name, repo_name)
                else:
                    orchestrator.run_repo_scan(repo_name=repo_name)
            else:
                if effective_tools is not None:
                    net = [
                        t
                        for t in effective_tools
                        if TOOL_DOMAIN_MAP.get(t) == "network"
                    ]
                    repo_tools = [
                        t
                        for t in effective_tools
                        if TOOL_DOMAIN_MAP.get(t) != "network"
                    ]
                    if net:
                        orchestrator.run_segment("network")
                    for tool_name in repo_tools:
                        orchestrator.run_tool_on_all_repos(tool_name)
                else:
                    orchestrator.run_full_scan()
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")

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

        from core.tools.registry import discover_tools

        discover_tools(self.repl.base_path, project_name=self.repl.active_project)
        try:
            self._cmd_run_inner(tool_name, remaining, timeout, args)
        finally:
            discover_tools(self.repl.base_path)

    def _cmd_run_inner(
        self,
        tool_name: str,
        remaining: list[str],
        timeout: int,
        orig_args: list[str],
    ) -> None:
        """Inner run logic — runs after registry is refreshed with project overrides."""
        assert self.repl.active_project is not None
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
            doc_ids = _ingest_result(self.repl, result)
            if doc_ids:
                self.repl.console.print(
                    f"[green]✓ Ingested {len(doc_ids)} findings[/green]"
                )
                sqlite_store, run_id = self._create_sqlite_run(orig_args)
                _enrich_results(
                    self.repl, doc_ids, sqlite_store=sqlite_store, run_id=run_id
                )
            else:
                self.repl.console.print("[yellow]No findings to ingest.[/yellow]")

    # ------------------------------------------------------------------
    # Private — nmap scan flow
    # ------------------------------------------------------------------

    def _execute_nmap_scan(
        self,
        profile_name: str,
        executor: ToolExecutor | None = None,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("nmap")
        assert tool is not None
        if executor is None:
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

    def _execute_semgrep_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("semgrep")
        assert tool is not None
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

    def _execute_osv_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("osv-scanner")
        assert tool is not None
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
    # Private — pip-audit scan flow
    # ------------------------------------------------------------------

    def _execute_pip_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("pip-audit")
        assert tool is not None
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

    def _execute_npm_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("npm-audit")
        assert tool is not None
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

    def _execute_composer_audit_scan(
        self,
        repo_name: str,
        repo_path: str,
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("composer-audit")
        assert tool is not None
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
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("gitleaks")
        assert tool is not None
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

    def _execute_zap_scan(
        self,
        repo_name: str,
        base_url: str,
        endpoints: dict[str, list[str]],
        auto_approve: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> ToolResult:
        assert self.repl.active_project is not None
        tool = tool_registry.get_tool("zap")
        assert tool is not None
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
        parts = [f"{by_sev[s]} {s}" for s in ("high", "medium", "low") if by_sev.get(s)]
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

    def _create_sqlite_run(self, args: list[str]) -> tuple[object, int | None]:
        """Instantiate SQLiteStore and create a run record.

        Returns (sqlite_store, run_id).  On failure returns (None, None).
        """
        assert self.repl.active_project is not None
        try:
            from core.store.sqlite_store import SQLiteStore

            store = SQLiteStore(self.repl.base_path, self.repl.active_project)
            run_id = store.create_run({"args": args})
            return store, run_id
        except Exception as exc:
            self.repl.console.print(f"[yellow]SQLite unavailable:[/yellow] {exc}")
            return None, None

    def _make_orchestrator(self, run_id: int | None = None):
        """Create a ScanOrchestrator for the active project."""
        from core.tools.executor import ToolExecutor
        from core.tools.orchestrator import ScanOrchestrator

        assert self.repl.active_project is not None
        executor = ToolExecutor(
            project_name=self.repl.active_project,
            base_path=Path(self.repl.base_path),
        )
        return ScanOrchestrator(
            project=self.repl.active_project,
            tool_registry=tool_registry,
            tool_executor=executor,
            event_bus=self.repl.event_bus,
            run_id=run_id,
            factory=ToolWrapperFactory(),
            console=self.repl.console,
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
