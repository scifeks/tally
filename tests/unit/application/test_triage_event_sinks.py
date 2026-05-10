"""Unit tests for Phase 6.1 triage event sinks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from domain.pipeline import triage_events as te
from infrastructure.events.bus import EventBus
from infrastructure.events.types import EOS, BusEvent
from web.adapters.event_bus_triage_sink import (
    TRIAGE_JOB_ID,
    TRIAGE_STREAM,
    EventBusTriageSink,
)


@pytest.mark.asyncio
async def test_event_bus_sink_publishes_to_subscriber() -> None:
    bus = EventBus()
    await bus.register_job(TRIAGE_JOB_ID, TRIAGE_STREAM)
    sub_id, queue = await bus.subscribe(TRIAGE_JOB_ID)
    sink = EventBusTriageSink(bus)

    await asyncio.to_thread(
        sink.emit,
        te.RunStarted(scan_run_id=42, project_id=7, message="hello"),
    )

    item = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(item, BusEvent)
    assert item.stream == "triage"
    assert item.event_type == "run_started"
    assert item.payload["scan_run_id"] == 42
    assert item.payload["project_id"] == 7
    assert item.payload["message"] == "hello"
    assert "id" not in item.payload
    assert "timestamp" not in item.payload

    await bus.unsubscribe(TRIAGE_JOB_ID, sub_id)
    await bus.close_job(TRIAGE_JOB_ID)


@pytest.mark.asyncio
async def test_event_bus_sink_swallows_publish_failures() -> None:
    """The sink must never raise; bus publish errors are suppressed."""
    bus = EventBus()  # no job registered → publish_threadsafe will UnknownJob
    sink = EventBusTriageSink(bus)
    sink.emit(te.RunCompleted(scan_run_id=1, project_id=1, processed_count=3))


@pytest.mark.asyncio
async def test_event_bus_sink_publishes_run_completed_payload() -> None:
    bus = EventBus()
    await bus.register_job(TRIAGE_JOB_ID, TRIAGE_STREAM)
    _, queue = await bus.subscribe(TRIAGE_JOB_ID)
    sink = EventBusTriageSink(bus)

    await asyncio.to_thread(
        sink.emit,
        te.RunCompleted(
            scan_run_id=9,
            project_id=2,
            message="done",
            processed_count=12,
        ),
    )

    item = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(item, BusEvent)
    assert item.event_type == "run_completed"
    assert item.payload["processed_count"] == 12
    assert isinstance(item.ts, datetime)
    assert item.ts.tzinfo == UTC

    await bus.close_job(TRIAGE_JOB_ID)
    sentinel = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert sentinel is EOS


def test_run_failed_event_type_name() -> None:
    """RunFailed maps to the documented ``triage_failed`` SSE event type."""
    event = te.RunFailed(scan_run_id=1, project_id=1, error="boom")
    assert te.event_type_name(event) == "triage_failed"


@pytest.mark.asyncio
async def test_event_bus_sink_publishes_run_failed_payload() -> None:
    bus = EventBus()
    await bus.register_job(TRIAGE_JOB_ID, TRIAGE_STREAM)
    _, queue = await bus.subscribe(TRIAGE_JOB_ID)
    sink = EventBusTriageSink(bus)

    await asyncio.to_thread(
        sink.emit,
        te.RunFailed(
            scan_run_id=42,
            project_id=7,
            error="db timeout",
            failed_at_finding_id=99,
            completed_count=3,
            total_count=10,
            resumable=True,
            message="Triage failed",
        ),
    )

    item = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert isinstance(item, BusEvent)
    assert item.event_type == "triage_failed"
    p = item.payload
    assert p["scan_run_id"] == 42
    assert p["project_id"] == 7
    assert p["error"] == "db timeout"
    assert p["failed_at_finding_id"] == 99
    assert p["completed_count"] == 3
    assert p["total_count"] == 10
    assert p["resumable"] is True
    assert p["message"] == "Triage failed"
    # Envelope fields stripped (BusEvent supplies its own id/timestamp).
    assert "id" not in p
    assert "timestamp" not in p

    await bus.close_job(TRIAGE_JOB_ID)
