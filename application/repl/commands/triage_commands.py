"""REPL commands for AI triage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.agent_sandbox.compose import ComposeGenerationError
from application.agent_sandbox.container import (
    AgentContainerStartError,
    containers_running,
    ensure_containers,
    teardown_containers,
)
from application.agent_sandbox.image import (
    AgentImageBuildError,
    DockerNotAvailableError,
    ensure_image,
    image_ready,
    rebuild_image,
)
from application.locking import JobBusy
from application.mcp.token_minting import mint_bearer_token
from application.repl.adapters.console_triage_event_sink import (
    ConsoleTriageEventSink,
)
from application.repl.commands.scan_commands import _parse_shared_mode_flags
from application.repl.exceptions import ReplArgumentError
from application.triage.factory import resolve_triage_config
from application.triage.orchestrator import (
    run_triage_batch_only,
    run_triage_dry_run,
)
from application.triage.runner import NoScanRunError
from core.config import ConfigManager
from factories.persistence import (
    ProjectNotFound,
    create_triage_service,
    load_active_repos,
    make_store,
)

if TYPE_CHECKING:
    from application.repl.interface import REPL


class TriageCommands:
    def __init__(
        self,
        repl: REPL,
    ) -> None:
        self._repl = repl

    _TRIAGE_SUB_COMMANDS = {"start", "resume"}

    def cmd_triage(self, _cmd: str, args: list[str]) -> None:
        if args and args[0] in self._TRIAGE_SUB_COMMANDS:
            sub = args.pop(0)
            dispatch = {
                "start": self.cmd_triage_start,
                "resume": self.cmd_triage_resume,
            }
            dispatch[sub](_cmd, args)
            return

        if "--rebuild-container" in args:
            self._rebuild_container()
            return

        if not self._repl.active_project:
            self._repl.console.print("[red]Error:[/red] No active project set.")
            return
        readiness = self._repl.triage_readiness
        if not readiness.enabled:
            self._repl.console.print(f"[red]Error:[/red] {readiness.reason}")
            return
        if "--batch" in args:
            run_repo, finding_repo, triage_repo, audit_repo = make_store(
                self._repl.base_path, self._repl.active_project
            )
            repos = load_active_repos(self._repl.base_path, self._repl.active_project)
            repo_paths = {r.name: Path(r.path) for r in repos if r.path}
            count = run_triage_batch_only(
                self._repl.active_project,
                self._repl.tool_registry,
                app_root=Path(self._repl.base_path),
                run_repo=run_repo,
                finding_repo=finding_repo,
                triage_repo=triage_repo,
                audit_repo=audit_repo,
                repo_paths=repo_paths,
            )
            self._repl.console.print(f"Created {count} batches")
            return
        elif "--dry-run" in args:
            run_repo, finding_repo, triage_repo, audit_repo = make_store(
                self._repl.base_path, self._repl.active_project
            )
            repos = load_active_repos(self._repl.base_path, self._repl.active_project)
            repo_paths = {r.name: Path(r.path) for r in repos if r.path}
            count = run_triage_dry_run(
                self._repl.active_project,
                self._repl.tool_registry,
                app_root=Path(self._repl.base_path),
                run_repo=run_repo,
                finding_repo=finding_repo,
                triage_repo=triage_repo,
                audit_repo=audit_repo,
                repo_paths=repo_paths,
            )
            self._repl.console.print(f"Rendered {count} batch prompt(s); see DEBUG log")
            return
        self._repl.console.print(
            "\n[bold yellow]Warning: prompt injection risk"
            "[/bold yellow]\n"
            "Triage reads source files and findings from scanned"
            " repositories\n"
            "and includes that content verbatim in prompts sent"
            " to an LLM.\n"
            "Malicious content in those files could manipulate"
            " the model into\n"
            "writing incorrect triage results or reading"
            " sensitive files.\n"
            "\nOnly proceed if you trust the repositories in"
            " this project.\n"
        )
        confirm = input("Proceed with triage? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            self._repl.console.print("[yellow]Triage cancelled.[/yellow]")
            return

        repos = load_active_repos(
            self._repl.base_path,
            self._repl.active_project,
        )
        repo_paths = {r.name: Path(r.path) for r in repos if r.path}

        if not self._ensure_image():
            return
        if not self._ensure_containers(repo_paths):
            return

        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None or row.archived_at:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return
        try:
            service = create_triage_service(
                self._repl.project_registry,
                row.id,
                repo_paths=repo_paths,
            )
        except ProjectNotFound:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return
        try:
            handle = service.start_triage(
                base_path=self._repl.base_path,
                project_id=row.id,
                project_name=self._repl.active_project,
                tool_registry=self._repl.tool_registry,
                event_sink=ConsoleTriageEventSink(self._repl.console),
            )
        except NoScanRunError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except JobBusy as exc:
            self._repl.console.print(
                "[yellow]Another triage is in progress"
                f" (holder={exc.current_holder}).[/yellow]"
            )
            return
        result = handle.result.result()

        if result.get("status") == "rate_limited":
            self._repl.console.print(
                f"[yellow]Triage paused: rate limited after "
                f"{result['sessions_run']} session(s). "
                f"Resume with: triage --resume[/yellow]"
            )
            return

        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )

    def _ensure_image(self) -> bool:
        """Check sandbox image; build if missing. Returns False on error."""
        app_root = Path(self._repl.base_path)
        try:
            if not image_ready():
                self._repl.console.print(
                    "[yellow]Building triage agent image"
                    " (this may take a few minutes)..."
                    "[/yellow]"
                )
            built = ensure_image(app_root)
            if built:
                self._repl.console.print("[green]Triage agent image ready.[/green]")
        except DockerNotAvailableError:
            self._repl.console.print(
                "[red]Error:[/red] Docker is not installed or not running."
            )
            return False
        except AgentImageBuildError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return False
        return True

    def _ensure_containers(
        self,
        repo_paths: dict[str, Path] | None = None,
    ) -> bool:
        """Check sandbox containers; start if not running.

        Returns False on error.
        """
        app_root = Path(self._repl.base_path)
        project = self._repl.active_project
        if not project:
            return False
        try:
            if not containers_running(app_root):
                self._repl.console.print(
                    "[yellow]Starting triage containers...[/yellow]"
                )
            resolved = resolve_triage_config(app_root=app_root)
            started = ensure_containers(
                app_root,
                provider=resolved.provider_name,
                base_url=resolved.base_url,
                model=resolved.model,
                repo_paths=repo_paths,
            )
            if started:
                self._repl.console.print("[green]Triage containers ready.[/green]")
        except DockerNotAvailableError:
            self._repl.console.print(
                "[red]Error:[/red] Docker is not installed or not running."
            )
            return False
        except (
            ComposeGenerationError,
            AgentContainerStartError,
        ) as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return False
        return True

    def _rebuild_container(self) -> None:
        """Tear down containers and rebuild the sandbox image."""
        app_root = Path(self._repl.base_path)
        self._repl.console.print("Stopping triage agent containers...")
        try:
            teardown_containers(app_root)
            rebuild_image(app_root)
        except DockerNotAvailableError:
            self._repl.console.print(
                "[red]Error:[/red] Docker is not installed or not running."
            )
            return
        except AgentImageBuildError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except FileNotFoundError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        self._repl.console.print("[green]Triage agent image rebuilt.[/green]")

    def cmd_triage_start(self, _cmd: str, args: list[str]) -> None:
        """Start triage.

        triage start [--interactive | --background]
            [--billing plan|api] [--api-key-override <key>]
        """
        if not self._repl.active_project:
            self._repl.console.print("[red]Error:[/red] No active project set.")
            return

        try:
            interaction_mode, billing_method, api_key_override = (
                _parse_shared_mode_flags(args)
            )
        except ReplArgumentError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return

        if args:
            self._repl.console.print(f"[red]Error:[/red] Unknown flag: {args[0]}")
            return

        if interaction_mode is None:
            interaction_mode = "interactive"

        if interaction_mode == "interactive" and billing_method is not None:
            self._repl.console.print(
                "[red]Error:[/red] --billing requires --background mode"
            )
            return

        readiness = self._repl.triage_readiness
        if not readiness.enabled:
            self._repl.console.print(f"[red]Error:[/red] {readiness.reason}")
            return

        if interaction_mode == "interactive":
            if not self._ensure_image():
                return
            repos = load_active_repos(
                self._repl.base_path,
                self._repl.active_project,
            )
            repo_paths = {r.name: Path(r.path) for r in repos if r.path}
            if not self._ensure_containers(repo_paths):
                return

        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None or row.archived_at:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return

        repos = load_active_repos(
            self._repl.base_path,
            self._repl.active_project,
        )
        repo_paths = {r.name: Path(r.path) for r in repos if r.path}

        try:
            service = create_triage_service(
                self._repl.project_registry,
                row.id,
                repo_paths=repo_paths,
            )
        except ProjectNotFound:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return

        try:
            handle = service.start_triage(
                base_path=self._repl.base_path,
                project_id=row.id,
                project_name=self._repl.active_project,
                tool_registry=self._repl.tool_registry,
                event_sink=ConsoleTriageEventSink(self._repl.console),
                interaction_mode=interaction_mode,
                billing_method=billing_method,
                api_key=api_key_override,
            )
        except NoScanRunError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except JobBusy as exc:
            self._repl.console.print(
                "[yellow]Another triage is in progress"
                f" (holder={exc.current_holder}).[/yellow]"
            )
            return

        if interaction_mode == "interactive":
            self._print_interactive_triage_info(
                self._repl.base_path, handle.scan_run_id
            )

        result = handle.result.result()

        if result.get("status") == "rate_limited":
            self._repl.console.print(
                f"[yellow]Triage paused: rate limited after "
                f"{result['sessions_run']} session(s). "
                f"Resume with: triage resume[/yellow]"
            )
            return

        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )

    def cmd_triage_resume(self, _cmd: str, args: list[str]) -> None:
        """Resume triage.

        triage resume <scan_run_id>
            [--interactive | --background]
            [--billing plan|api] [--api-key-override <key>]
        """
        if not self._repl.active_project:
            self._repl.console.print("[red]Error:[/red] No active project set.")
            return

        if not args:
            self._repl.console.print(
                "[red]Usage:[/red] triage resume <scan_run_id> [options]"
            )
            return

        try:
            scan_run_id = int(args[0])
        except ValueError:
            self._repl.console.print("[red]Error:[/red] scan_run_id must be an integer")
            return

        remaining_args = args[1:]
        try:
            interaction_mode, billing_method, api_key_override = (
                _parse_shared_mode_flags(remaining_args)
            )
        except ReplArgumentError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return

        if remaining_args:
            self._repl.console.print(
                f"[red]Error:[/red] Unknown flag: {remaining_args[0]}"
            )
            return

        if interaction_mode is None:
            interaction_mode = "interactive"

        if interaction_mode == "interactive" and billing_method is not None:
            self._repl.console.print(
                "[red]Error:[/red] --billing requires --background mode"
            )
            return

        readiness = self._repl.triage_readiness
        if not readiness.enabled:
            self._repl.console.print(f"[red]Error:[/red] {readiness.reason}")
            return

        if interaction_mode == "interactive":
            if not self._ensure_image():
                return
            repos = load_active_repos(
                self._repl.base_path,
                self._repl.active_project,
            )
            repo_paths = {r.name: Path(r.path) for r in repos if r.path}
            if not self._ensure_containers(repo_paths):
                return

        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None or row.archived_at:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return

        repos = load_active_repos(
            self._repl.base_path,
            self._repl.active_project,
        )
        repo_paths = {r.name: Path(r.path) for r in repos if r.path}

        try:
            service = create_triage_service(
                self._repl.project_registry,
                row.id,
                repo_paths=repo_paths,
            )
        except ProjectNotFound:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return

        try:
            handle = service.resume_triage(
                base_path=self._repl.base_path,
                project_id=row.id,
                project_name=self._repl.active_project,
                scan_run_id=scan_run_id,
                tool_registry=self._repl.tool_registry,
                event_sink=ConsoleTriageEventSink(self._repl.console),
                interaction_mode=interaction_mode,
                billing_method=billing_method,
                api_key=api_key_override,
            )
        except JobBusy as exc:
            self._repl.console.print(
                "[yellow]Another triage is in progress"
                f" (holder={exc.current_holder}).[/yellow]"
            )
            return

        if interaction_mode == "interactive":
            self._print_interactive_triage_info(self._repl.base_path, scan_run_id)

        result = handle.result.result()

        if result.get("status") == "rate_limited":
            self._repl.console.print(
                f"[yellow]Triage paused: rate limited after "
                f"{result['sessions_run']} session(s).[/yellow]"
            )
            return

        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )

    def _print_interactive_triage_info(self, base_path: str, scan_run_id: int) -> None:
        """Mint an MCP bearer token and print connection info for interactive triage."""
        token = mint_bearer_token(
            f"triage-interactive-{scan_run_id}",
            base_path=Path(base_path),
        )
        cfg = ConfigManager(base_path).global_config
        mcp_url = f"http://{cfg.mcp.host}:{cfg.mcp.port}/mcp"

        self._repl.console.print(f"\n  mcp_url:          {mcp_url}")
        self._repl.console.print(f"  mcp_bearer_token: {token}\n")
