"""Web adapter: project ReportEvents onto the async EventBus.

Report runs on a worker thread separate from the FastAPI asyncio loop,
so ``publish_threadsafe`` hops back into the bus's loop. Bus publish
failures are swallowed so report generation never fails when nothing listens.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime

from application.ports.event_publisher import EventPublisherPort
from domain.pipeline.bus_event import BusEvent, new_event_id
from domain.pipeline.report_events import ReportEvent, event_type_name

REPORT_JOB_ID = "report"
REPORT_STREAM = "report"


def _payload_for(event: ReportEvent) -> dict:
    """Flatten a report event dataclass into the BusEvent payload mapping.

    ``id`` and ``timestamp`` stay on the wire so SSE consumers have a
    stable per-event identifier for React keys and audit logging.
    """
    return dataclasses.asdict(event)


class EventBusReportSink:
    """Publish report events to a process-singleton EventBus."""

    def __init__(
        self, publisher: EventPublisherPort, *, job_id: str = REPORT_JOB_ID
    ) -> None:
        self._publisher = publisher
        self._job_id = job_id

    def emit(self, event: ReportEvent) -> None:
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=REPORT_STREAM,
            event_type=event_type_name(event),
            payload=_payload_for(event),
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._publisher.publish_threadsafe(bus_event)
