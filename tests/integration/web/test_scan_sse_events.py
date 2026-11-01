"""Integration test for scan phase lifecycle SSE events.

Verifies the sink-to-bus path: EventBusScanSink publishes PhaseStarted
and PhaseCompleted events through the EventBus, and a subscriber
receives them with correct event_type and payload fields.

Uses a direct EventBus subscription rather than a full HTTP SSE stream.
The triage SSE integration tests (test_sse_attempts.py) use the same
approach for the same reason: httpx.AsyncClient + ASGITransport blocks
on long-lived streams.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from application.mcp.ingest_service import McpIngestService
from infrastructure.events.bus import EventBus
from infrastructure.events.types import BusEvent
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from web.adapters.event_bus_scan_sink import SCAN_JOB_ID, EventBusScanSink

pytestmark = pytest.mark.integration


async def _next_event(queue: asyncio.Queue, *, timeout: float = 2.0) -> BusEvent:
    item = await asyncio.wait_for(queue.get(), timeout=timeout)
    assert isinstance(item, BusEvent)
    return item


def _make_service(db_path: Path, sink: EventBusScanSink) -> McpIngestService:
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    return McpIngestService(
        finding_repo=FindingRepository(factory),
        run_repo=RunRepository(factory),
        scan_event_sink=sink,
    )


def _create_run(db_path: Path) -> int:
    factory = ConnectionFactory(db_path)
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO scan_runs (project_id, status, created_at)"
            " VALUES (1, 'running', '2026-01-01T00:00:00')"
        )
        assert cur.lastrowid is not None
        return cur.lastrowid


@pytest.mark.asyncio
async def test_phase_events_reach_bus_subscriber(tmp_path: Path) -> None:
    bus = EventBus()
    await bus.register_job(SCAN_JOB_ID, stream="scan")
    sub_id, queue = await bus.subscribe(SCAN_JOB_ID)

    sink = EventBusScanSink(bus)
    db = tmp_path / "findings.db"
    svc = _make_service(db, sink)
    run_id = _create_run(db)

    svc.start_scan_phase(project=None, run_id=run_id, phase="recon", usage_pool="plan")
    svc.mark_scan_phase_complete(
        project=None,
        run_id=run_id,
        phase="recon",
        status="completed",
        metadata={"findings_count": 3},
    )

    started = await _next_event(queue)
    assert started.event_type == "phase_started"
    assert started.payload["run_id"] == run_id
    assert started.payload["phase"] == "recon"
    assert started.payload["attempt_number"] == 1

    completed = await _next_event(queue)
    assert completed.event_type == "phase_completed"
    assert completed.payload["run_id"] == run_id
    assert completed.payload["phase"] == "recon"
    assert completed.payload["findings_count"] == 3
    assert completed.payload["attempt_number"] == 1

    await bus.unsubscribe(SCAN_JOB_ID, sub_id)
