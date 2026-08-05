"""Unit tests for ConsoleTriageEventSink."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.repl.adapters.console_triage_event_sink import (
    ConsoleTriageEventSink,
)
from domain.pipeline.triage_events import (
    BatchCreated,
    RunStarted,
)


class TestConsoleTriageEventSink:
    def test_batch_created_prints_message(self) -> None:
        console = MagicMock()
        sink = ConsoleTriageEventSink(console)
        event = BatchCreated(
            scan_run_id=1,
            project_id=1,
            batch_id=0,
            segment="sast",
            findings_count=5,
            message="Batched 5 batch(es) for semgrep/repo1/sast",
        )
        sink.emit(event)
        console.print.assert_called_once_with(
            "  Batched 5 batch(es) for semgrep/repo1/sast"
        )

    def test_non_batch_events_are_ignored(self) -> None:
        console = MagicMock()
        sink = ConsoleTriageEventSink(console)
        event = RunStarted(
            scan_run_id=1,
            project_id=1,
            message="Triage starting",
        )
        sink.emit(event)
        console.print.assert_not_called()
