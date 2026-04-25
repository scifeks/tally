"""Web adapter: project TriageEvents onto the async EventBus.

Phase 6.2: triage runs on a worker ``threading.Thread`` separate from
the FastAPI asyncio loop, so we use ``publish_threadsafe`` to hop back
into the bus's loop. Adapters never raise — bus publish failures
(closed job, disconnected loop) are swallowed so triage never fails
because nothing is listening.

The ``stream`` field on ``BusEvent`` already includes ``"triage"`` (see
``infrastructure/events/types.py``). All triage events publish under
``job_id="triage"`` so a single SSE subscriber on that job receives the
full lifecycle stream and filters by ``payload['project_id']`` /
``payload['scan_run_id']``.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime

from domain.pipeline.triage_events import TriageEvent, event_type_name
from infrastructure.events.bus import EventBus
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import BusEvent

TRIAGE_JOB_ID = "triage"
TRIAGE_STREAM = "triage"


def _payload_for(event: TriageEvent) -> dict:
    """Flatten a triage event dataclass into the BusEvent payload mapping."""
    payload = dataclasses.asdict(event)
    payload.pop("id", None)
    payload.pop("timestamp", None)
    return payload


class EventBusTriageSink:
    """Publish triage events to a process-singleton EventBus."""

    def __init__(self, bus: EventBus, *, job_id: str = TRIAGE_JOB_ID) -> None:
        self._bus = bus
        self._job_id = job_id

    def emit(self, event: TriageEvent) -> None:
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=TRIAGE_STREAM,
            event_type=event_type_name(event),
            payload=_payload_for(event),
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._bus.publish_threadsafe(bus_event)
