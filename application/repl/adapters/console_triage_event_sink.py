"""REPL adapter for triage lifecycle events.

Prints batch progress to the Rich console so the REPL shows feedback
when triage is started from the terminal. Non-batch events are
discarded; the REPL does not display them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.pipeline.triage_events import BatchCreated

if TYPE_CHECKING:
    from rich.console import Console

    from domain.pipeline.triage_events import TriageEvent


class ConsoleTriageEventSink:
    """Prints triage batch progress to a Rich Console."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def emit(self, event: TriageEvent) -> None:
        if isinstance(event, BatchCreated):
            self._console.print(f"  {event.message}")
