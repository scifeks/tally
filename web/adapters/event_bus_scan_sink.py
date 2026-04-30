"""Web adapter: project ScanEvents onto the async EventBus.

Phase 5.2: scans run on a worker ``threading.Thread`` separate from the
FastAPI asyncio loop, so we use ``publish_threadsafe`` to hop back into
the bus's loop. Adapters never raise — bus publish failures (closed
job, disconnected loop) are swallowed so a scan never fails because
nothing is listening.

The ``stream`` field on ``BusEvent`` is a ``Literal`` that already
includes ``"scan"`` (see ``infrastructure/events/types.py``). All scan
events publish under ``job_id="scan"`` so a single SSE subscriber on
that job receives the full lifecycle stream and filters by
``payload['project_id']`` / ``payload['run_id']``.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime

from application.tools.scan_run_registry import get_scan_run_registry
from domain.pipeline.scan_events import ScanEvent, ToolStarted, event_type_name
from infrastructure.events.bus import EventBus
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import BusEvent

SCAN_JOB_ID = "scan"
SCAN_STREAM = "scan"


def _payload_for(event: ScanEvent) -> dict:
    """Flatten a scan event dataclass into the BusEvent payload mapping."""
    payload = dataclasses.asdict(event)
    # ``id`` and ``timestamp`` belong on the envelope, not the payload.
    payload.pop("id", None)
    payload.pop("timestamp", None)
    return payload


class EventBusScanSink:
    """Publish scan events to a process-singleton EventBus."""

    def __init__(self, bus: EventBus, *, job_id: str = SCAN_JOB_ID) -> None:
        self._bus = bus
        self._job_id = job_id

    def emit(self, event: ScanEvent) -> None:
        # Mirror ToolStarted into the run registry so SSE subscribers
        # connecting mid-scan see the active (repo, tool) in the
        # snapshot frame instead of waiting for the next event.
        if isinstance(event, ToolStarted) and event.run_id is not None:
            with contextlib.suppress(Exception):
                get_scan_run_registry().set_current(
                    event.run_id, repo=event.repo, tool=event.tool
                )
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=SCAN_STREAM,
            event_type=event_type_name(event),
            payload=_payload_for(event),
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._bus.publish_threadsafe(bus_event)
