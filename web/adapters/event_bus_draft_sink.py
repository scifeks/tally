"""Web adapter: project DraftEvents onto the async EventBus (Phase 7.5).

Draft generation runs on a worker ``threading.Thread`` separate from the
FastAPI asyncio loop, so we use ``publish_threadsafe`` to hop back into
the bus's loop. Adapters never raise — bus publish failures are swallowed
so draft generation never fails because nothing is listening.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime

from domain.pipeline.report_events import DraftEvent, event_type_name
from infrastructure.events.bus import EventBus
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import BusEvent

DRAFT_JOB_ID = "report_draft"
DRAFT_STREAM = "report_draft"


def _payload_for(event: DraftEvent) -> dict:
    """Flatten a draft event dataclass into the BusEvent payload mapping."""
    payload = dataclasses.asdict(event)
    payload.pop("id", None)
    payload.pop("timestamp", None)
    return payload


class EventBusDraftSink:
    """Publish draft events to a process-singleton EventBus."""

    def __init__(self, bus: EventBus, *, job_id: str = DRAFT_JOB_ID) -> None:
        self._bus = bus
        self._job_id = job_id

    def emit(self, event: DraftEvent) -> None:
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=DRAFT_STREAM,
            event_type=event_type_name(event),
            payload=_payload_for(event),
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._bus.publish_threadsafe(bus_event)
