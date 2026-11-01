"""Scan execution commands for the tally REPL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from rich.table import Table

from application.locking import JobBusy
from application.mcp.token_minting import mint_bearer_token
from application.project.repositories_service import ProjectRepositoriesService
from application.repl.adapters.orchestrator_display import OrchestratorDisplay
from application.repl.adapters.rich_console_prompt import RichConsolePromptAdapter
from application.repl.adapters.stdout_progress_reporter import StdoutProgressReporter
from application.repl.commands.scan_result_presenter import ScanResultPresenter
from application.repl.exceptions import ReplArgumentError
from application.tools.dast_prerequisites import DastPrerequisiteService
from application.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from application.tools.orchestrator import ScanCancelled
from application.url_inventory.url_list_service import (
    ProjectNotFound as UrlProjectNotFound,
)
from core.config import ConfigManager
from core.project_paths import ProjectPaths
from domain.scans.vuln_scanner_registry import (
    UnknownScannerSkill,
    group_by_family,
    list_scanners,
    resolve_display_slug,
)
from factories.persistence import (
    create_finding_repo,
    create_overrides_repo,
    create_repo_repo,
    create_scan_repos,
    create_url_finding_repo,
    create_url_list_service,
    load_active_repos,
)
from factories.scanning import (
    create_git_diff,
    create_subprocess_runner,
    get_scan_service,
)
from infrastructure.tools.cli_runner import CliToolRunner

if TYPE_CHECKING:
    from application.repl.interface import REPL
    from core.config.schemas import Repository


InteractionMode = Literal["interactive", "background"]
BillingMethod = Literal["plan", "api"]


def _parse_shared_mode_flags(
    args: list[str],
) -> tuple[InteractionMode | None, BillingMethod | None, str | None]:
    """Parse --interactive, --background, --billing, --api-key-override.

    Mutates *args* in-place, removing consumed tokens so callers can parse
    remaining flags (e.g. --only, --exclude) from the leftovers.

    Returns (interaction_mode, billing_method, api_key_override).
    Raises ReplArgumentError on validation errors.
    """
    interaction_mode: InteractionMode | None = None
    billing_method: BillingMethod | None = None
    api_key_override: str | None = None

    consumed: list[int] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--interactive":
            interaction_mode = "interactive"
            consumed.append(i)
            i += 1
        elif arg == "--background":
            interaction_mode = "background"
            consumed.append(i)
            i += 1
        elif arg == "--billing":
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise ReplArgumentError("--billing requires a value")
            raw_billing = args[i + 1]
            if raw_billing == "plan" or raw_billing == "api":
                billing_method = raw_billing
            else:
                raise ReplArgumentError(
                    f"billing method must be 'plan' or 'api', got {raw_billing!r}"
                )
            consumed.extend([i, i + 1])
            i += 2
        elif arg == "--api-key-override":
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise ReplArgumentError("--api-key-override requires a value")
            api_key_override = args[i + 1]
            consumed.extend([i, i + 1])
            i += 2
        else:
            i += 1

    for idx in reversed(consumed):
        del args[idx]

    return interaction_mode, billing_method, api_key_override


class ScanCommands:
    """Handlers for tool scan execution commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    def cmd_scan_skills(self, _cmd: str, _args: list[str]) -> None:
        """scan skills - Display available vulnerability scanner skills."""
        table = Table(title="Available Vulnerability Scanner Skills")
        table.add_column("Display Slug", style="cyan")
        table.add_column("Family", style="magenta")
        table.add_column("Description", style="green")

        for entry in list_scanners():
            table.add_row(entry.display_slug, entry.family, entry.description)

        self.repl.console.print(table)

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

    _SCAN_SUB_COMMANDS = {"skills", "start", "resume"}

    def cmd_scan(self, _cmd: str, args: list[str]) -> None:
        """scan [skills | start | resume] [options]"""
        if args and args[0] in self._SCAN_SUB_COMMANDS:
            sub = args.pop(0)
            dispatch = {
                "skills": self.cmd_scan_skills,
                "start": self.cmd_scan_start,
                "resume": self.cmd_scan_resume,
            }
            dispatch[sub](_cmd, args)
            return

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
        since_commit_val: str | None = None
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
            elif arg.startswith("--since-commit="):
                since_commit_val = arg[15:]
            else:
                unrecognized.append(arg)

        if unrecognized:
            self.repl.console.print(
                f"[red]Unrecognized argument(s):[/red] {', '.join(unrecognized)}\n"
                "Usage: scan [--repo=<repo,...>] [--tool=<tool,...>]"
                " [--skip-tools=<tool,...>] [--domain=<domain,...>]"
                " [--since-commit=<commit>] [--skip-enrichment] [--yes]"
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
                since_commit=since_commit_val,
                git_diff=(create_git_diff() if since_commit_val else None),
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
            handle.result.result()
        except ScanCancelled:
            self.repl.console.print("[yellow]Scan cancelled.[/yellow]")
            return
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except Exception as exc:
            self.repl.console.print(f"[red]Scan failed:[/red] {exc}")
            return

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
            cli_tool_runner=CliToolRunner(create_subprocess_runner()),
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
        """Return tool names for a full repository scan."""
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
        """Prompt when DAST tools run without prior discovery output."""
        if auto_approve:
            return tools

        assert self.repl.active_project is not None
        repos = self._active_repos()
        target_repos = (
            [r for r in repos if r.name in repo_names]
            if repo_names is not None
            else repos
        )

        service = DastPrerequisiteService()
        check = service.check(
            tools,
            target_repos,
            lambda r: self._repo_has_url_findings(r, project_id),
        )
        if check is None:
            return tools

        missing_str = ", ".join(r.name for r in check.missing_repos)
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
            to_prepend = service.resolve_discovery_tools(check.missing_repos)
            return service.prepend_prerequisites(to_prepend, tools)
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
            self.repl.console.print(f"[green]Exported to:[/green] {export_path}")
        except Exception as exc:
            self.repl.console.print(f"[red]Export failed:[/red] {exc}")

    def cmd_scan_start(self, _cmd: str, args: list[str]) -> None:
        """Start a scan.

        scan start [--only x,y] [--exclude x,y]
            [--interactive | --background]
            [--billing plan|api] [--api-key-override <key>]
        """
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        try:
            interaction_mode, billing_method, api_key_override, only, exclude = (
                self._parse_mode_flags(args)
            )
        except ReplArgumentError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        if interaction_mode is None:
            interaction_mode = "interactive"

        project_name = self.repl.active_project

        row = self.repl.project_registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            self.repl.console.print(
                f"[red]Error:[/red] project {project_name!r} not found"
            )
            return

        project_id = row.id
        base_path = str(self.repl.base_path)

        repos = load_active_repos(base_path, project_name)
        if not repos:
            self.repl.console.print(
                f"[red]Error:[/red] project {project_name!r} has no active repos"
            )
            return

        if interaction_mode == "interactive":
            self._print_interactive_scan_info(base_path, project_name)
            return

        self._schedule_scan_launch(
            project_id=project_id,
            project_name=project_name,
            base_path=base_path,
            interaction_mode=interaction_mode,
            billing_method=billing_method,
            api_key_override=api_key_override,
            only=only or None,
            exclude=exclude or None,
            adversarial=False,
        )

    def _print_interactive_scan_info(self, base_path: str, project_name: str) -> None:
        """Mint an MCP bearer token and print connection info for interactive scan."""
        token = mint_bearer_token(
            f"scan-interactive-{project_name}",
            base_path=Path(base_path),
        )
        cfg = ConfigManager(base_path).global_config
        mcp_url = f"http://{cfg.mcp.host}:{cfg.mcp.port}/mcp"

        self.repl.console.print(
            "[green]Interactive scan ready.[/green]\n"
            "Paste the connection info below into your Claude Code session "
            "and run /tally-scan-external.\n"
        )
        self.repl.console.print(f"  mcp_url:          {mcp_url}")
        self.repl.console.print(f"  mcp_bearer_token: {token}")

    def _schedule_scan_launch(
        self,
        *,
        project_id: int,
        project_name: str,
        base_path: str,
        interaction_mode: InteractionMode,
        billing_method: BillingMethod | None,
        api_key_override: str | None,
        only: list[str] | None,
        exclude: list[str] | None,
        adversarial: bool,
        run_id: int | None = None,
    ) -> None:
        """Create or reuse a scan row and launch via ScanBackgroundLauncher.

        Shared by cmd_scan_start and cmd_scan_resume. When ``run_id`` is
        provided the row already exists (resume path); otherwise a new row
        is created after all cheap validations pass.
        """
        from application.anthropic.mode_availability import (
            BackgroundModeAvailabilityService,
        )
        from application.mcp.ingest_service import McpIngestService
        from application.scans.background_launcher import ScanBackgroundLauncher

        paths = ProjectPaths.from_canonical(self.repl.base_path, project_name)
        run_repo = create_scan_repos(paths.findings_db)[0]
        finding_repo = create_finding_repo(paths.findings_db)

        cfg = ConfigManager(base_path).global_config
        mcp_service = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
        )
        from application.repl.adapters.console_scan_event_sink import (
            ConsoleScanEventSink,
        )

        launcher = ScanBackgroundLauncher(
            mcp_service=mcp_service,
            availability=BackgroundModeAvailabilityService(cfg),
            config=cfg,
            scan_phase_repo=mcp_service,
            scan_event_sink=ConsoleScanEventSink(),
            scan_run_status_repo=run_repo,
        )

        is_new = run_id is None
        if is_new:
            run_id = run_repo.create(
                project_id=project_id,
                repo_ids=[],
                tool_ids=["claudecode"],
                domains=["llm"],
                skip_enrichment=True,
                status="queued",
            )

        try:
            launcher.launch(
                run_id=run_id,
                project_name=project_name,
                base_path=base_path,
                interaction_mode=interaction_mode,
                billing_method=billing_method,
                only=only,
                exclude=exclude,
                adversarial=adversarial,
                api_key_source=api_key_override,
            )
        except ValueError as exc:
            run_repo.set_status(run_id, "failed")
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        verb = "started" if is_new else "resumed"
        self.repl.console.print(
            f"[green]Background scan {verb}:[/green] run_id={run_id}"
        )

    def cmd_scan_resume(self, _cmd: str, args: list[str]) -> None:
        """Resume a scan.

        scan resume <run_id>
            [--interactive | --background]
            [--billing plan|api] [--api-key-override <key>]
        """
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        if not args:
            self.repl.console.print("[red]Usage:[/red] scan resume <run_id> [options]")
            return

        try:
            run_id = int(args[0])
        except ValueError:
            self.repl.console.print("[red]Error:[/red] run_id must be an integer")
            return

        remaining_args = args[1:]

        try:
            interaction_mode, billing_method, api_key_override, only, exclude = (
                self._parse_mode_flags(remaining_args)
            )
        except ReplArgumentError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        if only or exclude:
            self.repl.console.print(
                "[red]Error:[/red] --only and --exclude are not supported for resume"
            )
            return

        if interaction_mode is None:
            interaction_mode = "background"

        if interaction_mode != "background":
            self.repl.console.print(
                "[red]Error:[/red] scan resume requires --background mode"
            )
            return

        project_name = self.repl.active_project

        row = self.repl.project_registry.resolve_by_name(project_name)
        if row is None or row.archived_at:
            self.repl.console.print(
                f"[red]Error:[/red] project {project_name!r} not found"
            )
            return

        project_id = row.id
        base_path = str(self.repl.base_path)
        paths = ProjectPaths.from_canonical(self.repl.base_path, project_name)

        run_repo = create_scan_repos(paths.findings_db)[0]
        scan_row = run_repo.get(run_id)
        if scan_row is None or scan_row.project_id != project_id:
            self.repl.console.print(f"[red]Error:[/red] scan run {run_id} not found")
            return

        if scan_row.status not in ("failed", "running", "rate_limited"):
            self.repl.console.print(
                f"[red]Error:[/red] run {run_id} status is "
                f"{scan_row.status!r}; cannot resume"
            )
            return

        from application.mcp.ingest_service import McpIngestService

        finding_repo = create_finding_repo(paths.findings_db)
        mcp_service = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
        )

        scan_config = mcp_service.get_scan_config(project=project_name, run_id=run_id)
        only_stored = scan_config.get("only") or None
        exclude_stored = scan_config.get("exclude") or None
        adversarial = scan_config.get("adversarial_verification", False)

        self._schedule_scan_launch(
            project_id=project_id,
            project_name=project_name,
            base_path=base_path,
            interaction_mode=interaction_mode,
            billing_method=billing_method,
            api_key_override=api_key_override,
            only=only_stored,
            exclude=exclude_stored,
            adversarial=adversarial,
            run_id=run_id,
        )

    def _parse_mode_flags(
        self, args: list[str]
    ) -> tuple[
        InteractionMode | None,
        BillingMethod | None,
        str | None,
        list[str] | None,
        list[str] | None,
    ]:
        """Parse mode, billing, and filter flags.

        Returns (interaction_mode, billing_method, api_key_override, only, exclude).
        Raises ReplArgumentError on validation errors.
        """
        interaction_mode, billing_method, api_key_override = _parse_shared_mode_flags(
            args
        )

        only: list[str] | None = None
        exclude: list[str] | None = None

        i = 0
        while i < len(args):
            flag = args[i]
            if flag in ("--only", "--exclude"):
                if i + 1 >= len(args) or args[i + 1].startswith("--"):
                    raise ReplArgumentError(f"{flag} requires a comma-separated value")
                values = [v.strip() for v in args[i + 1].split(",") if v.strip()]
                if not values:
                    raise ReplArgumentError(f"{flag} requires a comma-separated value")
                if flag == "--only":
                    only = values
                else:
                    exclude = values
                i += 2
            else:
                i += 1

        if only and exclude:
            raise ReplArgumentError("--only and --exclude are mutually exclusive")

        if interaction_mode == "interactive" and billing_method is not None:
            raise ReplArgumentError("--billing requires --background mode")

        if only:
            try:
                only = self._resolve_scanner_slugs(only)
            except UnknownScannerSkill as exc:
                raise ReplArgumentError(str(exc)) from exc

        if exclude:
            try:
                exclude = self._resolve_scanner_slugs(exclude)
            except UnknownScannerSkill as exc:
                raise ReplArgumentError(str(exc)) from exc

        return interaction_mode, billing_method, api_key_override, only, exclude

    @staticmethod
    def _resolve_scanner_slugs(items: list[str]) -> list[str]:
        """Expand family names to display slugs and validate."""
        families = group_by_family()
        result: list[str] = []
        for item in items:
            if item in families:
                result.extend(e.display_slug for e in families[item])
            else:
                resolve_display_slug(item)
                result.append(item)
        return list(dict.fromkeys(result))
