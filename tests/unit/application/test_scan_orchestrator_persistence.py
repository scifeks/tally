"""Unit tests for ScanOrchestrator persistence and event emission."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.locking.cancellation import CancellationToken
from application.ports.scan_event_sink import NullScanEventSink
from application.tools.orchestrator import ScanCancelled, ScanOrchestrator
from domain.pipeline import scan_events as se


class _RecordingSink(NullScanEventSink):
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:  # type: ignore[override]
        self.events.append(event)


def _make_orchestrator(
    *,
    run_id: int | None = 1,
    project_id: int | None = 1,
    sink: NullScanEventSink | None = None,
    cancel: CancellationToken | None = None,
    repo: MagicMock | None = None,
) -> ScanOrchestrator:
    with (
        patch("core.config.manager.ConfigManager"),
        patch("application.tools.orchestrator._build_tool_execution_config"),
    ):
        return ScanOrchestrator(
            project="test-project",
            tool_registry=MagicMock(),
            tool_executor=MagicMock(base_path="/tmp"),
            event_bus=MagicMock(),
            prompt=MagicMock(),
            run_id=run_id,
            event_sink=sink,
            cancel_token=cancel,
            run_repository=repo,
            project_id=project_id,
        )


@patch("application.tools.orchestrator.FullScan")
def test_run_emits_started_and_completed(mock_full_scan: MagicMock) -> None:
    summary = MagicMock(ingested_total=5)
    mock_full_scan.return_value.execute.return_value = summary
    sink = _RecordingSink()

    o = _make_orchestrator(sink=sink)
    o.run_full_scan()

    assert len(sink.events) == 2
    assert isinstance(sink.events[0], se.RunStarted)
    assert isinstance(sink.events[1], se.RunCompleted)


@patch("application.tools.orchestrator.FullScan")
def test_run_persists_status_timestamps_findings(
    mock_full_scan: MagicMock,
) -> None:
    summary = MagicMock(ingested_total=12)
    mock_full_scan.return_value.execute.return_value = summary
    repo = MagicMock()

    o = _make_orchestrator(repo=repo)
    o.run_full_scan()

    assert repo.set_status.call_count >= 2
    assert repo.set_started_at.called
    assert repo.set_finished_at.called


@patch("application.tools.orchestrator.FullScan")
def test_failure_emits_run_failed_and_persists_failed(
    mock_full_scan: MagicMock,
) -> None:
    mock_full_scan.return_value.execute.side_effect = RuntimeError("boom")
    sink = _RecordingSink()

    o = _make_orchestrator(sink=sink)
    with pytest.raises(RuntimeError):
        o.run_full_scan()

    assert len(sink.events) == 2
    assert isinstance(sink.events[0], se.RunStarted)
    assert isinstance(sink.events[1], se.RunFailed)


@patch("application.tools.orchestrator.FullScan")
def test_cancellation_emits_run_cancelled_and_persists_cancelled(
    mock_full_scan: MagicMock,
) -> None:
    mock_full_scan.return_value.execute.side_effect = ScanCancelled
    sink = _RecordingSink()
    token = CancellationToken()

    o = _make_orchestrator(sink=sink, cancel=token)
    with pytest.raises(ScanCancelled):
        o.run_full_scan()

    assert len(sink.events) == 2
    assert isinstance(sink.events[0], se.RunStarted)
    assert isinstance(sink.events[1], se.RunCancelled)


@patch("application.tools.orchestrator.FullScan")
def test_no_run_id_skips_persistence(mock_full_scan: MagicMock) -> None:
    """REPL parity: when run_id is None, persistence is skipped."""
    summary = MagicMock(ingested_total=3)
    mock_full_scan.return_value.execute.return_value = summary

    o = _make_orchestrator(run_id=None, repo=None)
    result = o.run_full_scan()

    assert result is not None


def test_orchestrator_installs_cancel_token_on_executor() -> None:
    token = CancellationToken()
    executor = MagicMock(base_path="/tmp")

    with (
        patch("core.config.manager.ConfigManager"),
        patch("application.tools.orchestrator._build_tool_execution_config"),
    ):
        ScanOrchestrator(
            project="p",
            tool_registry=MagicMock(),
            tool_executor=executor,
            event_bus=MagicMock(),
            prompt=MagicMock(),
            run_id=1,
            cancel_token=token,
        )

    executor.set_cancel_token.assert_called_once_with(token)
