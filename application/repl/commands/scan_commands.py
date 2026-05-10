"""Scan execution commands for the tally REPL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import JobBusy
from application.project.repositories_service import ProjectRepositoriesService
from application.repl.adapters.orchestrator_display import OrchestratorDisplay
from application.repl.adapters.rich_console_prompt import RichConsolePromptAdapter
from application.repl.adapters.stdout_progress_reporter import StdoutProgressReporter
from application.repl.commands.scan_result_presenter import ScanResultPresenter
from application.scans.scans_service import ProjectNotFound
from application.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from application.tools.orchestrator import ScanCancelled
from application.tools.scan_service import get_scan_service
from application.url_inventory.url_list_service import (
    ProjectNotFound as UrlProjectNotFound,
)
from core.detection.noir import noir_skip_reason
from core.project_paths import ProjectPaths
from factories.persistence import (
    create_finding_repo,
    create_overrides_repo,
    create_repo_repo,
    create_scan_repos,
    create_scans_service,
    create_url_finding_repo,
    create_url_list_service,
)
from infrastructure.tools.runner import SubprocessRunner

if TYPE_CHECKING:
    from application.repl.interface import REPL
    from core.config.schemas import Repository


class ScanCommands:
    """Handlers for tool scan execution commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    def _active_repos(self) -> list[Repository]:
        """Return active repos for the REPL's current project."""
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            return []
        service = ProjectRepositoriesService(
            self.repl.project_registry, self.repl.config
        )
        return service.list_active(row.id)

    def cmd_scan(self, _cmd: str, args: list[str]) -> None:
        """scan [--repo=<repo,...>] [--tool=<tool,...>] [--domain=<domain,...>]"""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        from application.tools.registry import discover_tools

        paths = ProjectPaths.from_canonical(
            self.repl.base_path, self.repl.active_project
        )
        overrides_repo = create_overrides_repo(paths.findings_db)
        discover_tools(
            self.repl.tool_registry,
            self.repl.base_path,
            project_name=self.repl.active_project,
            overrides_repo=overrides_repo,
        )
        try:
            self._cmd_scan_inner(args)
        finally:
            discover_tools(self.repl.tool_registry, self.repl.base_path)

    def _cmd_scan_inner(self, args: list[str]) -> None:
        """Inner scan logic. Runs after registry is refreshed."""
        from application.rag.ingestor import get_tool_domain
        from domain.tools.constants import DOMAINS

        auto_approve = "--yes" in args
        args = [a for a in args if a != "--yes"]

        skip_enrichment = "--skip-enrichment" in args
        args = [a for a in args if a != "--skip-enrichment"]

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
                " [--skip-tools=<tool,...>] [--domain=<domain,...>]"
                " [--skip-enrichment] [--yes]"
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
            repos = self._active_repos()
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
            known = set(self.repl.tool_registry.list_tool_names())
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
            known = set(self.repl.tool_registry.list_tool_names())
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
            all_configured = list(self.repl.tool_registry.list_tool_names())
            candidates = (
                list(requested_tools) if requested_tools is not None else all_configured
            )
            if requested_domains is not None:
                candidates = [
                    t for t in candidates if get_tool_domain(t) in requested_domains
                ]
            effective_tools = candidates

        project_id = self._resolve_project_id()
        paths = ProjectPaths.from_canonical(
            self.repl.base_path, self.repl.active_project
        )

        # The DAST-without-discovery prompt asks the user a question
        # and may rewrite effective_tools before dispatch.
        if effective_tools is not None:
            effective_tools = self._maybe_warn_dast_without_discovery(
                effective_tools,
                repo_names,
                auto_approve,
                project_id,
            )
            if effective_tools is None:
                return

        run_repo, chat_repo, profiles_repo, _ = create_scan_repos(paths.findings_db)

        finding_repo = create_finding_repo(paths.findings_db)
        repo_repo = create_repo_repo(paths.findings_db)
        url_finding_repo = create_url_finding_repo(paths.findings_db)

        try:
            handle = get_scan_service().start_scan(
                project_id=project_id,
                project_name=self.repl.active_project,
                base_path=str(self.repl.base_path),
                tool_registry=self.repl.tool_registry,
                run_repo=run_repo,
                chat_session_repo=chat_repo,
                profiles_repo=profiles_repo,
                finding_repo=finding_repo,
                repo_repo=repo_repo,
                url_finding_repo=url_finding_repo,
                repo_ids=tuple(repo_names or ()),
                tool_ids=tuple(effective_tools or ()),
                skip_tool_ids=tuple(skip_tools),
                skip_enrichment=skip_enrichment,
                prompt=RichConsolePromptAdapter(auto_approve=auto_approve),
                reporter=StdoutProgressReporter(),
                display=OrchestratorDisplay(self.repl.console),
                run_args={"args": args},
            )
        except JobBusy as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        try:
            summary = handle.result.result()
        except ScanCancelled:
            self.repl.console.print("[yellow]Scan cancelled.[/yellow]")
            return
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except Exception as exc:
            self.repl.console.print(f"[red]Scan failed:[/red] {exc}")
            return

        if summary.findings_by_tool:
            try:
                create_scans_service(
                    self.repl.project_registry, project_id
                ).record_run_tool_counts(handle.run_id, summary.findings_by_tool)
            except ProjectNotFound:
                pass

    def _resolve_project_id(self) -> int:
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            raise ValueError(f"project not found: {self.repl.active_project}")
        return row.id

    def cmd_run(self, _cmd: str, args: list[str]) -> None:
        """Execute a tool with raw arguments."""
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

        paths = ProjectPaths.from_canonical(
            self.repl.base_path, self.repl.active_project
        )
        overrides_repo = create_overrides_repo(paths.findings_db)
        discover_tools(
            self.repl.tool_registry,
            self.repl.base_path,
            project_name=self.repl.active_project,
            overrides_repo=overrides_repo,
        )
        try:
            self._cmd_run_inner(tool_name, remaining, timeout)
        finally:
            discover_tools(self.repl.tool_registry, self.repl.base_path)

    def _cmd_run_inner(
        self,
        tool_name: str,
        remaining: list[str],
        timeout: int,
    ) -> None:
        """Inner run logic. Runs after registry is refreshed with project overrides."""
        assert self.repl.active_project is not None
        tool = self.repl.tool_registry.get_tool(tool_name)
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
            prompt=RichConsolePromptAdapter(),
            subprocess_runner=SubprocessRunner(),
            reporter=StdoutProgressReporter(),
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

    def _maybe_warn_dast_without_discovery(
        self,
        tools: list[str],
        repo_names: list[str] | None,
        auto_approve: bool,
        project_id: int,
    ) -> list[str] | None:
        """Warn when DAST tools are requested but no discovery output exists.

        DAST tools (zap, xsstrike, dalfox) work best when an endpoint
        discovery tool (katana, noir) has already produced OAS3 output.
        Checks whether that output exists for the target repos and, when
        it does not, prompts the user to prepend discovery tools.

        Returns the (possibly expanded) effective tool list to execute, or
        ``None`` to indicate that the scan was canceled by the user.

        When ``auto_approve`` is True the warning is suppressed.
        """
        _dast_tools = {"zap", "xsstrike", "dalfox"}
        _discovery_tools = {"katana", "noir"}

        if not (_dast_tools & set(tools)):
            return tools
        if _discovery_tools & set(tools):
            return tools
        if auto_approve:
            return tools

        assert self.repl.active_project is not None
        repos = self._active_repos()
        target_repos = (
            [r for r in repos if r.name in repo_names]
            if repo_names is not None
            else repos
        )

        missing = [
            r
            for r in target_repos
            if r.crawl_enabled and not self._repo_has_url_findings(r, project_id)
        ]
        if not missing:
            return tools

        missing_str = ", ".join(r.name for r in missing)
        self.repl.console.print(
            f"\n[yellow]Warning:[/yellow] No endpoint discovery output found"
            f" for: {missing_str}.\n"
            "DAST tools work best with prior endpoint discovery output.\n"
        )
        self.repl.console.print(
            "  1. Run discovery first, then DAST [bold](recommended)[/bold]\n"
            "  2. Run DAST now without discovery output\n"
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
            # Prepend discovery tools: katana always, noir when supported.
            to_prepend: list[str] = ["katana"]
            if any(noir_skip_reason(r) is None for r in missing):
                to_prepend.append("noir")
            existing = [t for t in tools if t not in to_prepend]
            return to_prepend + existing
        # choice == "2": proceed without discovery
        return tools

    def _repo_has_url_findings(self, repo: object, project_id: int) -> bool:
        """Return True if *repo* has any ``url_findings`` rows."""
        repo_id = getattr(repo, "id", None)
        if not isinstance(repo_id, int):
            return False
        try:
            service = create_url_list_service(self.repl.project_registry, project_id)
        except UrlProjectNotFound:
            return False
        return service.repo_has_url_findings(repo_id)

    def _export_summary(self, summary, export_path: str) -> None:
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
