"""Web adapter: project DraftEvents onto the async EventBus.

Draft generation runs on a worker thread separate from the FastAPI asyncio
loop, so ``publish_threadsafe`` hops back into the bus's loop. Bus publish
failures are swallowed so draft generation never fails when nothing listens.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime

from application.ports.event_publisher import EventPublisherPort
from domain.pipeline.bus_event import BusEvent, new_event_id
from domain.pipeline.report_events import DraftEvent, event_type_name

DRAFT_JOB_ID = "report_draft"
DRAFT_STREAM = "report_draft"


def _payload_for(event: DraftEvent) -> dict:
    """Flatten a draft event dataclass into the BusEvent payload mapping.

    ``id`` and ``timestamp`` stay on the wire so SSE consumers have a
    stable per-event identifier for React keys and audit logging.
    """
    return dataclasses.asdict(event)


class EventBusDraftSink:
    """Publish draft events to a process-singleton EventBus."""

    def __init__(
        self, publisher: EventPublisherPort, *, job_id: str = DRAFT_JOB_ID
    ) -> None:
        self._publisher = publisher
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
            self._publisher.publish_threadsafe(bus_event)
