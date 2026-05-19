"""Domain events for report metadata updates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def _new_event_id() -> str:
    return str(uuid4())


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class _ReportUpdateEventBase:
    report_id: int
    project_id: int | None
    id: str = field(default_factory=_new_event_id)
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class ReportUpdated(_ReportUpdateEventBase):
    """Emitted after a successful metadata PATCH on a report."""

    display_name: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ReportUpdateFailed(_ReportUpdateEventBase):
    """Emitted when a metadata update fails."""

    error: str = ""


type ReportUpdateEvent = ReportUpdated | ReportUpdateFailed

_EVENT_TYPE_NAMES: dict[type, str] = {
    ReportUpdated: "report_updated",
    ReportUpdateFailed: "report_update_failed",
}


def event_type_name(event: ReportUpdateEvent) -> str:
    """Return the SSE event_type string for *event*."""
    return _EVENT_TYPE_NAMES[type(event)]
