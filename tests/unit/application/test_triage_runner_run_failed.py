"""Unit tests for the RunFailed emit path on TriageRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.triage.runner import TriageRunner
from domain.pipeline.triage_events import RunFailed
from domain.triage.entry import TriageBatchRow
from domain.triage.entry import TriageRunSummary as TriageRunSummaryRow


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def _make_runner(tmp_path: Path) -> tuple[TriageRunner, _RecordingSink, MagicMock]:
    sink = _RecordingSink()
    triage_repo = MagicMock()
    triage_repo.summarize_for_run.return_value = TriageRunSummaryRow(
        scan_run_id=7,
        status="running",
        started_at="2026-04-25T00:00:00Z",
        finished_at=None,
        total_findings=10,
        processed_findings=3,
        total_batches=4,
        counts_by_status={"pending": 1, "in_progress": 1, "completed": 2},
    )
    triage_repo.list_for_run.return_value = [
        TriageBatchRow(
            id=1,
            run_id=7,
            finding_ids=[101, 102],
            batch_data=[],
            status="completed",
            run_attempts=1,
            created_at=None,
            started_at=None,
            completed_at="2026-04-25T00:01:00Z",
        ),
        TriageBatchRow(
            id=2,
            run_id=7,
            finding_ids=[201],
            batch_data=[],
            status="in_progress",
            run_attempts=1,
            created_at=None,
            started_at="2026-04-25T00:02:00Z",
            completed_at=None,
        ),
        TriageBatchRow(
            id=3,
            run_id=7,
            finding_ids=[301],
            batch_data=[],
            status="pending",
            run_attempts=0,
            created_at=None,
            started_at=None,
            completed_at=None,
        ),
    ]
    runner = TriageRunner(
        project="proj",
        run_repo=MagicMock(),
        triage_repo=triage_repo,
        audit_repo=MagicMock(),
        app_root=tmp_path,
        event_sink=sink,
        project_id=42,
        triage_agent=MagicMock(),
    )
    return runner, sink, triage_repo


def test_emit_run_failed_populates_payload(tmp_path: Path) -> None:
    runner, sink, _ = _make_runner(tmp_path)
    runner._emit_run_failed(7, RuntimeError("db unavailable"))

    assert len(sink.events) == 1
    event = sink.events[0]
    assert isinstance(event, RunFailed)
    assert event.scan_run_id == 7
    assert event.project_id == 42
    assert event.error == "db unavailable"
    assert event.completed_count == 3
    assert event.total_count == 10
    assert event.resumable is True
    # First in-progress batch's first finding id surfaces as failed_at.
    assert event.failed_at_finding_id == 201


def test_emit_run_failed_falls_back_when_summary_missing(tmp_path: Path) -> None:
    runner, sink, triage_repo = _make_runner(tmp_path)
    triage_repo.summarize_for_run.return_value = None
    triage_repo.list_for_run.return_value = []

    runner._emit_run_failed(7, RuntimeError("boom"))

    assert len(sink.events) == 1
    event = sink.events[0]
    assert isinstance(event, RunFailed)
    assert event.error == "boom"
    assert event.completed_count == 0
    assert event.total_count == 0
    assert event.resumable is False
    assert event.failed_at_finding_id is None


def test_emit_run_failed_uses_exception_class_when_message_empty(
    tmp_path: Path,
) -> None:
    runner, sink, _ = _make_runner(tmp_path)
    runner._emit_run_failed(7, RuntimeError())

    assert len(sink.events) == 1
    event = sink.events[0]
    assert isinstance(event, RunFailed)
    assert event.error == "RuntimeError"


def test_run_emits_run_failed_and_reraises_on_uncaught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: an exception in _run_batch_loop emits RunFailed + re-raises."""
    runner, sink, _ = _make_runner(tmp_path)

    # Make batch() return a stable run_id without touching the DB.
    monkeypatch.setattr(runner, "batch", lambda: (7, 0))
    # Stub MCP config so _write_mcp_config doesn't need a real venv.
    fake_path = tmp_path / ".mcp.json"
    fake_path.write_text("{}")
    monkeypatch.setattr(runner, "_write_mcp_config", lambda _run_id: fake_path)

    def _explode(*_a, **_kw):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(runner, "_run_batch_loop", _explode)

    with pytest.raises(RuntimeError, match="db unavailable"):
        runner.run()

    failed_events = [e for e in sink.events if isinstance(e, RunFailed)]
    assert len(failed_events) == 1
    assert failed_events[0].error == "db unavailable"
    assert failed_events[0].resumable is True
