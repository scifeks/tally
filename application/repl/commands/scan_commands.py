"""Scan execution commands for the tally REPL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from application.repl.commands.scan_result_presenter import ScanResultPresenter
from application.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from application.tools.factory import ToolWrapperFactory
from application.tools.registry import tool_registry

if TYPE_CHECKING:
    from application.repl.interface import REPL


class ScanCommands:
    """Handlers for tool scan execution commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_scan(self, _cmd: str, args: list[str]) -> None:
        """scan [--repo=<repo,...>] [--tool=<tool,...>] [--domain=<domain,...>]"""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        from application.tools.registry import discover_tools

        discover_tools(self.repl.base_path, project_name=self.repl.active_project)
        try:
            self._cmd_scan_inner(args)
        finally:
            discover_tools(self.repl.base_path)

    def _cmd_scan_inner(self, args: list[str]) -> None:
        """Inner scan logic — runs after registry is refreshed."""
        from application.rag.ingestor import get_tool_domain
        from domain.tools.constants import DOMAINS

        auto_approve = "--yes" in args
        args = [a for a in args if a != "--yes"]

        repo_val: str | None = None
        tool_val: str | None = None
        domain_val: str | None = None
        skip_tools_val: str | None = None
        unrecognized: list[str] = []

        for arg in args:
            if arg.startswith("--repo="):
                repo_val = arg[7:]
            elif arg.startswith("--tool="):
                tool_val = arg[7:]
            elif arg.startswith("--domain="):
                domain_val = arg[9:]
            elif arg.startswith("--skip-tools="):
                skip_tools_val = arg[13:]
            else:
                unrecognized.append(arg)

        if unrecognized:
            self.repl.console.print(
                f"[red]Unrecognized argument(s):[/red] {', '.join(unrecognized)}\n"
                "Usage: scan [--repo=<repo,...>] [--tool=<tool,...>]"
                " [--skip-tools=<tool,...>] [--domain=<domain,...>] [--yes]"
            )
            return

        if tool_val is not None and skip_tools_val is not None:
            self.repl.console.print(
                "[red]--tool and --skip-tools are mutually exclusive.[/red]"
            )
            return

        assert self.repl.active_project is not None

        # Validate --repo
        repo_names: list[str] | None = None
        if repo_val is not None:
            requested_repos = [r.strip() for r in repo_val.split(",") if r.strip()]
            repos = self.repl.config.load_repositories(self.repl.active_project)
            repo_map = {r.name.lower(): r.name for r in repos}
            invalid_repos = [r for r in requested_repos if r.lower() not in repo_map]
            if invalid_repos:
                names = sorted(repo_map.values())
                self.repl.console.print(
                    f"[red]Unknown repository:[/red] {', '.join(invalid_repos)}\n"
                    f"Configured repos: {', '.join(names) or 'none'}"
                )
                return
            repo_names = [repo_map[r.lower()] for r in requested_repos]

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

        # Validate --skip-tools
        skip_tools: set[str] = set()
        if skip_tools_val is not None:
            parsed_skips = [t.strip() for t in skip_tools_val.split(",") if t.strip()]
            known = set(tool_registry.list_tool_names())
            invalid_skips = [t for t in parsed_skips if t not in known]
            if invalid_skips:
                self.repl.console.print(
                    f"[red]Unknown tool(s):[/red] {', '.join(invalid_skips)}\n"
                    f"Configured tools: {', '.join(sorted(known))}"
                )
                return
            skip_tools = set(parsed_skips)

        # Compute effective tool list (--tool and/or --domain only)
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

        _finding_repo, run_repo, run_id = self._create_sqlite_run(args)
        orchestrator = self._make_orchestrator(run_id=run_id, auto_approve=auto_approve)
        if orchestrator is None:
            return

        accumulated_fbt: dict[str, int] = {}

        def _merge_fbt(summary) -> None:  # type: ignore[no-untyped-def]
            for tool, count in summary.findings_by_tool.items():
                accumulated_fbt[tool] = accumulated_fbt.get(tool, 0) + count

        try:
            if repo_names is not None:
                if effective_tools is not None:
                    effective_tools = self._maybe_warn_zap_without_noir(
                        effective_tools,
                        repo_names,
                        auto_approve,
                        orchestrator,
                    )
                    if effective_tools is None:
                        return
                    for repo_name in repo_names:
                        for _i, tool_name in enumerate(effective_tools):
                            _merge_fbt(
                                orchestrator.run_tool_on_repo(
                                    tool_name,
                                    repo_name,
                                    remaining_peers=len(effective_tools) - _i - 1,
                                )
                            )
                else:
                    for repo_name in repo_names:
                        _merge_fbt(
                            orchestrator.run_repo_scan(
                                repo_name=repo_name,
                                exclude_tools=skip_tools or None,
                            )
                        )
            else:
                if effective_tools is not None:
                    effective_tools = self._maybe_warn_zap_without_noir(
                        effective_tools,
                        None,
                        auto_approve,
                        orchestrator,
                    )
                    if effective_tools is None:
                        return
                    for _i, tool_name in enumerate(effective_tools):
                        _merge_fbt(
                            orchestrator.run_tool_on_all_repos(
                                tool_name,
                                remaining_peers=len(effective_tools) - _i - 1,
                            )
                        )
                else:
                    _merge_fbt(
                        orchestrator.run_full_scan(exclude_tools=skip_tools or None)
                    )
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")

        if run_id is not None and run_repo is not None and accumulated_fbt:
            run_repo.add_run_tools(  # type: ignore[union-attr]
                run_id,
                [{"tool": t, "findings_count": c} for t, c in accumulated_fbt.items()],
            )

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

        from application.tools.registry import discover_tools

        discover_tools(self.repl.base_path, project_name=self.repl.active_project)
        try:
            self._cmd_run_inner(tool_name, remaining, timeout)
        finally:
            discover_tools(self.repl.base_path)

    def _cmd_run_inner(
        self,
        tool_name: str,
        remaining: list[str],
        timeout: int,
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
    # Private — ZAP-without-Noir warning
    # ------------------------------------------------------------------

    def _maybe_warn_zap_without_noir(
        self,
        tools: list[str],
        repo_names: list[str] | None,
        auto_approve: bool,
        orchestrator: object,
    ) -> list[str] | None:
        """Warn when ZAP is requested but Noir OAS3 output is absent.

        Returns the (possibly expanded) effective tool list to execute, or
        ``None`` to indicate that the scan was cancelled by the user.

        When ``auto_approve`` is True the warning is suppressed and ZAP
        proceeds in quickscan mode.
        """
        if "zap" not in tools or "noir" in tools:
            return tools
        if auto_approve:
            return tools

        from infrastructure.tools.wrappers.local.zap import _find_noir_oas3

        assert self.repl.active_project is not None
        repos = self.repl.config.load_repositories(self.repl.active_project)
        target_repos = (
            [r for r in repos if r.name in repo_names]
            if repo_names is not None
            else repos
        )

        missing = [
            r.name
            for r in target_repos
            if not _find_noir_oas3(
                self.repl.base_path, self.repl.active_project, r.name
            )
        ]
        if not missing:
            return tools

        missing_str = ", ".join(missing)
        self.repl.console.print(
            f"\n[yellow]Warning:[/yellow] No Noir endpoint scan found"
            f" for: {missing_str}.\n"
            "ZAP will run in quickscan mode only and may miss"
            " API-only endpoints.\n"
        )
        self.repl.console.print(
            "  1. Run Noir first, then ZAP [bold](recommended)[/bold]\n"
            "  2. Run ZAP now in quickscan mode\n"
            "  3. Cancel\n"
        )
        try:
            raw = input("Enter choice [1/2/3] (default: 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        choice = raw if raw in ("1", "2", "3") else "1"

        if choice == "3":
            self.repl.console.print("[dim]Scan cancelled.[/dim]")
            return None
        if choice == "1":
            # Prepend noir so it runs first in the tool loop.
            return ["noir"] + [t for t in tools if t != "noir"]
        # choice == "2": proceed with ZAP only
        return tools

    # ------------------------------------------------------------------
    # Private — orchestrator factory and export
    # ------------------------------------------------------------------

    def _create_sqlite_run(self, args: list[str]) -> tuple[object, object, int | None]:
        """Instantiate repositories and create a run record.

        Returns (finding_repo, run_repo, run_id).
        On failure returns (None, None, None).
        """
        assert self.repl.active_project is not None
        try:
            from infrastructure.store import make_store

            run_repo, finding_repo, _, _ = make_store(
                self.repl.base_path, self.repl.active_project
            )
            run_id = run_repo.create_run({"args": args})
            return finding_repo, run_repo, run_id
        except Exception as exc:
            self.repl.console.print(f"[yellow]SQLite unavailable:[/yellow] {exc}")
            return None, None, None

    def _make_orchestrator(self, run_id: int | None = None, auto_approve: bool = False):
        """Create a ScanOrchestrator for the active project."""
        from application.tools.executor import ToolExecutor
        from application.tools.orchestrator import ScanOrchestrator

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
            auto_approve=auto_approve,
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
