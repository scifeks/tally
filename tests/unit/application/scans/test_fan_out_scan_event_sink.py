"""Tests for FanOutScanEventSink."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.ports.scan_event_sink import FanOutScanEventSink
from domain.pipeline import scan_events as se


class TestFanOutScanEventSink:
    def test_a_raising_sink_does_not_stop_the_next_one(self) -> None:
        broken = MagicMock()
        broken.emit.side_effect = RuntimeError("boom")
        healthy = MagicMock()
        event = se.RunStarted(run_id=1, project_id=1)

        FanOutScanEventSink([broken, healthy]).emit(event)

        healthy.emit.assert_called_once_with(event)
