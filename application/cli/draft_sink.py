"""CLI adapter for draft lifecycle events."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from domain.pipeline.report_events import DraftCompleted, DraftFailed, DraftStarted

if TYPE_CHECKING:
    from domain.pipeline.report_events import DraftEvent


class CliDraftEventSink:
    """Prints draft progress as plain text."""

    def emit(self, event: DraftEvent) -> None:
        if isinstance(event, DraftStarted):
            print(f"Generating {event.section}...")
        elif isinstance(event, DraftCompleted):
            print(f"Draft saved: {event.output_path}")
        elif isinstance(event, DraftFailed):
            print(f"Error: {event.error}", file=sys.stderr)
