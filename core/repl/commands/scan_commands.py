"""Scan execution commands for the tally REPL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.repl.commands.scan_result_presenter import ScanResultPresenter
from core.tools.base import ToolResult
from core.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from core.tools.factory import ToolWrapperFactory
from core.tools.registry import tool_registry

if TYPE_CHECKING:
    from core.repl.interface import REPL


def _enrich_results(
    repl: REPL,
    doc_ids: list[str],
    finding_repo: object = None,
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
            finding_repo=finding_repo,  # type: ignore[arg-type]
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
        repos = repl.config.load_repositories(repl.active_project)
        ingestor = FindingIngestor(rag_engine, repl.active_project, repositories=repos)
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
        """scan [--repo=<repo>] [--tool=<tool,...>] [--domain=<domain,...>]"""
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
        from core.rag.ingestor import get_tool_domain
        from core.tools.constants import DOMAINS

        auto_approve = "--yes" in args
        args = [a for a in args if a != "--yes"]

        repo_val: str | None = None
        tool_val: str | None = None
        domain_val: str | None = None
        unrecognized: list[str] = []

        for arg in args:
            if arg.startswith("--repo="):
                repo_val = arg[7:]
            elif arg.startswith("--tool="):
                tool_val = arg[7:]
            elif arg.startswith("--domain="):
                domain_val = arg[9:]
            else:
                unrecognized.append(arg)

        if unrecognized:
            self.repl.console.print(
                f"[red]Unrecognized argument(s):[/red] {', '.join(unrecognized)}\n"
                "Usage: scan [--repo=<repo>] [--tool=<tool,...>]"
                " [--domain=<domain,...>] [--yes]"
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

        # Validate --domain
        requested_domains: list[str] | None = None
        if domain_val is not None:
            requested_domains = [t.strip() for t in domain_val.split(",") if t.strip()]
            invalid_d = [t for t in requested_domains if t not in DOMAINS]
            if invalid_d:
                self.repl.console.print(
                    f"[red]Unknown domain(s):[/red] {', '.join(invalid_d)}\n"
                    f"Valid domains: {', '.join(sorted(DOMAINS))}"
                )
                return

        # Compute effective tool list (intersection of --tool and --domain filters)
        effective_tools: list[str] | None = None
        if requested_tools is not None or requested_domains is not None:
            all_configured = list(tool_registry.list_tool_names())
            candidates = (
                list(requested_tools) if requested_tools is not None else all_configured
            )
            if requested_domains is not None:
                candidates = [
                    t for t in candidates if get_tool_domain(t) in requested_domains
                ]
            effective_tools = candidates

        _finding_repo, run_id = self._create_sqlite_run(args)
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
                        t for t in effective_tools if get_tool_domain(t) == "network"
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
                        t for t in effective_tools if get_tool_domain(t) == "network"
                    ]
                    repo_tools = [
                        t for t in effective_tools if get_tool_domain(t) != "network"
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

        ScanResultPresenter(self.repl.console).present(result)

        if result.output_files:
            for path in result.output_files.values():
                self.repl.console.print(f"Output saved to: {path}")

        if self._ask_ingest():
            doc_ids = _ingest_result(self.repl, result)
            if doc_ids:
                self.repl.console.print(
                    f"[green]✓ Ingested {len(doc_ids)} findings[/green]"
                )
                finding_repo, run_id = self._create_sqlite_run(orig_args)
                _enrich_results(
                    self.repl, doc_ids, finding_repo=finding_repo, run_id=run_id
                )
            else:
                self.repl.console.print("[yellow]No findings to ingest.[/yellow]")

    # ------------------------------------------------------------------
    # Private — shared SCA result helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Private — UI helpers
    # ------------------------------------------------------------------

    def _ask_ingest(self) -> bool:
        try:
            answer = input("Ingest findings? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ("y", "yes")

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
        """Instantiate repositories and create a run record.

        Returns (finding_repo, run_id).  On failure returns (None, None).
        """
        assert self.repl.active_project is not None
        try:
            from core.store import make_store

            run_repo, finding_repo, _, _ = make_store(
                self.repl.base_path, self.repl.active_project
            )
            run_id = run_repo.create_run({"args": args})
            return finding_repo, run_id
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
