"""Web adapter: project ReportUpdated events onto the async EventBus.

Uses ``publish_threadsafe`` because the caller runs on a sync worker
thread, not the asyncio loop. Publish failures are swallowed so a
metadata PATCH never fails due to missing subscribers.
"""

from __future__ import annotations

import contextlib
import dataclasses
from datetime import UTC, datetime

from domain.reports.events import ReportUpdateEvent, event_type_name
from infrastructure.events.bus import EventBus
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import BusEvent

REPORT_UPDATE_JOB_ID = "report_update"
REPORT_UPDATE_STREAM = "report_update"


class EventBusReportUpdateSink:
    """Publish report update events to a process-singleton EventBus."""

    def __init__(self, bus: EventBus, *, job_id: str = REPORT_UPDATE_JOB_ID) -> None:
        self._bus = bus
        self._job_id = job_id

    def emit(self, event: ReportUpdateEvent) -> None:
        payload = dataclasses.asdict(event)
        bus_event = BusEvent(
            event_id=new_event_id(),
            job_id=self._job_id,
            stream=REPORT_UPDATE_STREAM,
            event_type=event_type_name(event),
            payload=payload,
            ts=datetime.now(UTC),
        )
        with contextlib.suppress(Exception):
            self._bus.publish_threadsafe(bus_event)
