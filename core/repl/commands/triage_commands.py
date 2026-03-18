"""REPL commands for AI triage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tally_mcp.orchestrator import run_triage, run_triage_batch_only, run_triage_dry_run

if TYPE_CHECKING:
    from core.repl.interface import REPL


class TriageCommands:
    def __init__(self, repl: REPL) -> None:
        self._repl = repl

    def cmd_triage(self, _cmd: str, args: list[str]) -> None:
        if not self._repl.active_project:
            self._repl.console.print("[red]Error:[/red] No active project set.")
            return
        if "--batch" in args:
            count = run_triage_batch_only(self._repl.active_project)
            self._repl.console.print(f"Created {count} batches")
            return
        elif "--dry-run" in args:
            count = run_triage_dry_run(self._repl.active_project)
            self._repl.console.print(
                f"Rendered {count} batch prompt(s) — see DEBUG log"
            )
            return
        result = run_triage(self._repl.active_project)
        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )
