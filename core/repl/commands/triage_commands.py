"""REPL commands for AI triage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.orchestrator import run_triage

if TYPE_CHECKING:
    from core.repl.interface import REPL


class TriageCommands:
    def __init__(self, repl: REPL) -> None:
        self._repl = repl

    def cmd_triage(self, _cmd: str, _args: list[str]) -> None:
        if not self._repl.active_project:
            self._repl.console.print("[red]Error:[/red] No active project set.")
            return
        result = run_triage(self._repl.active_project)
        self._repl.console.print(
            f"Triage: {result['sessions_run']} sessions run, "
            f"{result['success']} success, "
            f"{result['failed']} failed, "
            f"{result['incomplete']} incomplete"
        )
