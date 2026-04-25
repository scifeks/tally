"""Unit tests for Phase 5.2 scan event sinks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from application.ports.scan_event_sink import NullScanEventSink
from application.repl.adapters.console_scan_event_sink import (
    ConsoleScanEventSink,
)
from domain.pipeline import scan_events as se
from infrastructure.events.bus import EventBus
from infrastructure.events.types import EOS, BusEvent
from web.adapters.event_bus_scan_sink import (
    SCAN_JOB_ID,
    SCAN_STREAM,
    EventBusScanSink,
)


def test_null_sink_swallows_events() -> None:
    sink = NullScanEventSink()
    sink.emit(se.RunStarted(run_id=1, project_id=1))


def test_console_sink_is_a_null_sink() -> None:
    sink = ConsoleScanEventSink()
    sink.emit(se.RunStarted(run_id=1, project_id=1))


@pytest.mark.asyncio
async def test_event_bus_sink_publishes_to_subscriber() -> None:
    bus = EventBus()
    await bus.register_job(SCAN_JOB_ID, SCAN_STREAM)
    sub_id, queue = await bus.subscribe(SCAN_JOB_ID)
    sink = EventBusScanSink(bus)

    # publish_threadsafe schedules into the bus loop; await it indirectly
    # by running emission on a thread.
    await asyncio.to_thread(
        sink.emit,
        se.RunStarted(run_id=42, project_id=7, message="hello"),
    )

    item = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(item, BusEvent)
    assert item.stream == "scan"
    assert item.event_type == "run_started"
    assert item.payload["run_id"] == 42
    assert item.payload["project_id"] == 7
    assert item.payload["message"] == "hello"
    assert "id" not in item.payload  # envelope only
    assert "timestamp" not in item.payload  # envelope only

    await bus.unsubscribe(SCAN_JOB_ID, sub_id)
    await bus.close_job(SCAN_JOB_ID)


@pytest.mark.asyncio
async def test_event_bus_sink_swallows_publish_failures() -> None:
    """The sink must never raise — bus publish errors are suppressed."""
    bus = EventBus()  # no job registered → publish_threadsafe will UnknownJob
    sink = EventBusScanSink(bus)
    # No exception escapes, even with no registered job.
    sink.emit(se.RunCompleted(run_id=1, project_id=1, findings_count=3))


@pytest.mark.asyncio
async def test_event_bus_sink_publishes_run_completed_payload() -> None:
    bus = EventBus()
    await bus.register_job(SCAN_JOB_ID, SCAN_STREAM)
    _, queue = await bus.subscribe(SCAN_JOB_ID)
    sink = EventBusScanSink(bus)

    await asyncio.to_thread(
        sink.emit,
        se.RunCompleted(
            run_id=9,
            project_id=2,
            message="done",
            findings_count=12,
        ),
    )

    item = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(item, BusEvent)
    assert item.event_type == "run_completed"
    assert item.payload["findings_count"] == 12
    assert isinstance(item.ts, datetime)
    assert item.ts.tzinfo == UTC

    await bus.close_job(SCAN_JOB_ID)
    # Drain the EOS sentinel
    sentinel = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert sentinel is EOS
