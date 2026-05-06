"""REPL commands for AI triage."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.locking import JobBusy
from application.repl.adapters.console_triage_event_sink import ConsoleTriageEventSink
from application.triage.factory import (
    TriageProviderNotConfiguredError,
    ensure_triage_backend_configured,
)
from application.triage.orchestrator import (
    run_triage_batch_only,
    run_triage_dry_run,
)
from application.triage.readiness import triage_backend_label
from application.triage.runner import NoScanRunError
from application.triage.triage_service import ProjectNotFound, TriageService

if TYPE_CHECKING:
    from application.repl.interface import REPL
    from application.runtime import RuntimeDependencyService


class TriageCommands:
    def __init__(
        self,
        repl: REPL,
        runtime_service: RuntimeDependencyService | None = None,
    ) -> None:
        self._repl = repl
        self._runtime_service = runtime_service

    def cmd_triage(self, _cmd: str, args: list[str]) -> None:
        if not self._repl.active_project:
            self._repl.console.print("[red]Error:[/red] No active project set.")
            return
        try:
            provider = ensure_triage_backend_configured(
                app_root=Path(self._repl.base_path)
            )
        except (TriageProviderNotConfiguredError, NotImplementedError) as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        if (
            provider == "claude_code"
            and self._runtime_service is not None
            and not self._runtime_service.is_installed("claude")
        ):
            label = triage_backend_label(provider) or provider
            self._repl.console.print(f"[red]{label} is required for Triage[/red]")
            return
        if "--batch" in args:
            count = run_triage_batch_only(
                self._repl.active_project, self._repl.tool_registry
            )
            self._repl.console.print(f"Created {count} batches")
            return
        elif "--dry-run" in args:
            count = run_triage_dry_run(
                self._repl.active_project, self._repl.tool_registry
            )
            self._repl.console.print(f"Rendered {count} batch prompt(s); see DEBUG log")
            return
        self._repl.console.print(
            "\n[bold yellow]⚠ Prompt injection warning[/bold yellow]\n"
            "Triage reads source files and findings from scanned repositories\n"
            "and includes that content verbatim in prompts sent to an LLM.\n"
            "Malicious content in those files could manipulate the model into\n"
            "writing incorrect triage results or reading sensitive files.\n"
            "\nOnly proceed if you trust the repositories in this project.\n"
        )
        confirm = input("Proceed with triage? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            self._repl.console.print("[yellow]Triage cancelled.[/yellow]")
            return

        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None or row.archived_at:
            self._repl.console.print(
                f"[red]Error:[/red] project {self._repl.active_project!r} not found"
            )
            return
        try:
            service = TriageService.for_project(self._repl.project_registry, row.id)
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
                event_sink=ConsoleTriageEventSink(),
            )
        except NoScanRunError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return
        except JobBusy as exc:
            self._repl.console.print(
                f"[yellow]Another triage is in progress (holder={exc.current_holder})."
                f"[/yellow]"
            )
            return
        result = handle.result.result()
        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )
