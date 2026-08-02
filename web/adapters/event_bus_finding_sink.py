"""Web adapter: project finding events onto the async EventBus."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from application.ports.event_publisher import EventPublisherPort
from application.ports.finding_event_sink import FindingEvent
from domain.findings.events import (
    FindingCreated,
    FindingDeleted,
)
from domain.pipeline.bus_event import BusEvent, new_event_id
from web.api._finding_serialiser import serialise_finding

FINDING_JOB_ID = "finding"
FINDING_STREAM = "finding"


class EventBusFindingSink:
    """Publish finding events to a process-singleton EventBus."""

    def __init__(
        self, publisher: EventPublisherPort, *, job_id: str = FINDING_JOB_ID
    ) -> None:
        self._publisher = publisher
        self._job_id = job_id

    def emit(self, event: FindingEvent) -> None:
        if isinstance(event, FindingDeleted):
            payload: dict = {
                "id": event.finding_id,
                "project_id": event.project_id,
            }
            event_type = "finding_deleted"
        else:
            serialised = serialise_finding(
                event.finding,
                (event.is_locked, event.lock_holder),
            )
            payload = {
                **serialised,
                "project_id": event.project_id,
            }
            if isinstance(event, FindingCreated):
                event_type = "finding_created"
            else:
                event_type = "finding_updated"

        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=FINDING_STREAM,
            event_type=event_type,
            payload=payload,
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._publisher.publish_threadsafe(bus_event)
