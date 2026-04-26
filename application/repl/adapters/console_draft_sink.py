"""ConsoleDraftEventSink — REPL adapter for draft lifecycle events (Phase 7.5).

Replaces the inline ``console.status`` / ``console.print`` calls that were
previously scattered through the old ``draft_runner`` module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.pipeline.report_events import DraftCompleted, DraftFailed, DraftStarted

if TYPE_CHECKING:
    from rich.console import Console

    from domain.pipeline.report_events import DraftEvent


class ConsoleDraftEventSink:
    """Prints cosmetic draft progress to a Rich Console."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def emit(self, event: DraftEvent) -> None:
        if isinstance(event, DraftStarted):
            self._console.print(f"Generating {event.section}...")
        elif isinstance(event, DraftCompleted):
            self._console.print(f"[green]✓ Draft saved:[/green] {event.output_path}")
        elif isinstance(event, DraftFailed):
            self._console.print(f"[red]Error:[/red] {event.error}")
