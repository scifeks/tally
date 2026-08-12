"""REPL commands for AI triage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import JobBusy
from application.repl.adapters.console_triage_event_sink import (
    ConsoleTriageEventSink,
)
from application.triage.compose import ComposeGenerationError
from application.triage.container import (
    DockerNotAvailableError,
    TriageContainerStartError,
    TriageImageBuildError,
    ensure_triage_containers,
    ensure_triage_image,
    rebuild_triage_image,
    teardown_triage_containers,
    triage_containers_running,
    triage_image_ready,
)
from application.triage.orchestrator import (
    run_triage_batch_only,
    run_triage_dry_run,
)
from application.triage.runner import NoScanRunError
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

    def cmd_triage(self, _cmd: str, args: list[str]) -> None:
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
        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )

    def _ensure_image(self) -> bool:
        """Check triage image; build if missing. Returns False on error."""
        app_root = Path(self._repl.base_path)
        try:
            if not triage_image_ready():
                self._repl.console.print(
                    "[yellow]Building triage agent image"
                    " (this may take a few minutes)..."
                    "[/yellow]"
                )
            built = ensure_triage_image(app_root)
            if built:
                self._repl.console.print("[green]Triage agent image ready.[/green]")
        except DockerNotAvailableError:
            self._repl.console.print(
                "[red]Error:[/red] Docker is not installed or not running."
            )
            return False
        except TriageImageBuildError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return False
        return True

    def _ensure_containers(
        self,
        repo_paths: dict[str, Path] | None = None,
    ) -> bool:
        """Check triage containers; start if not running.

        Returns False on error.
        """
        app_root = Path(self._repl.base_path)
        project = self._repl.active_project
        if not project:
            return False
        try:
            if not triage_containers_running(app_root):
                self._repl.console.print(
                    "[yellow]Starting triage containers...[/yellow]"
                )
            started = ensure_triage_containers(app_root, project, repo_paths=repo_paths)
            if started:
                self._repl.console.print("[green]Triage containers ready.[/green]")
        except DockerNotAvailableError:
            self._repl.console.print(
                "[red]Error:[/red] Docker is not installed or not running."
            )
            return False
        except (
            ComposeGenerationError,
            TriageContainerStartError,
        ) as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return False
        return True

    def _rebuild_container(self) -> None:
        """Tear down containers and rebuild the triage agent image."""
        app_root = Path(self._repl.base_path)
        self._repl.console.print("Stopping triage agent containers...")
        try:
            teardown_triage_containers(app_root)
            rebuild_triage_image(app_root)
        except DockerNotAvailableError:
            self._repl.console.print(
                "[red]Error:[/red] Docker is not installed or not running."
            )
            return
        except TriageImageBuildError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except FileNotFoundError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        self._repl.console.print("[green]Triage agent image rebuilt.[/green]")
