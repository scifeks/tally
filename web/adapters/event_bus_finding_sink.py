"""Web adapter: project FindingUpdated events onto the async EventBus.

Findings PATCH executes on a worker thread (``asyncio.to_thread``)
separate from the FastAPI asyncio loop, so ``publish_threadsafe`` hops
back into the bus's loop. Bus publish failures are swallowed so a
patch never fails when nothing listens.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from domain.findings.events import FindingUpdated
from infrastructure.events.bus import EventBus
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import BusEvent
from web.api._finding_serialiser import serialise_finding

FINDING_JOB_ID = "finding"
FINDING_STREAM = "finding"


class EventBusFindingSink:
    """Publish finding events to a process-singleton EventBus."""

    def __init__(self, bus: EventBus, *, job_id: str = FINDING_JOB_ID) -> None:
        self._bus = bus
        self._job_id = job_id

    def emit(self, event: FindingUpdated) -> None:
        serialised = serialise_finding(
            event.finding, (event.is_locked, event.lock_holder)
        )
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=FINDING_STREAM,
            event_type="finding_updated",
            payload={**serialised, "project_id": event.project_id},
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._bus.publish_threadsafe(bus_event)
