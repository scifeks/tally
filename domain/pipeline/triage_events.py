"""Triage lifecycle events emitted by the triage runner (Phase 6.1).

These events are domain-pure: they carry no transport concerns. The
``TriageEventSink`` port (see ``application/ports/triage_event_sink.py``)
turns them into either no-op REPL discards (REPL adapter) or async
``BusEvent`` publishes for SSE fan-out (web adapter).

A "triage run" is identified by ``scan_run_id`` — the integer primary
key of the ``scan_runs`` row whose findings are being triaged. There is
no separate triage_id; ``triage_batches.run_id`` is the same column.

Field names match the SSE event payload catalogue in
``docs/roadmap/ui-planning/API/endpoints.md §15.2`` so adapters can do a
straight projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def _new_event_id() -> str:
    return str(uuid4())


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class _TriageEventBase:
    scan_run_id: int
    project_id: int | None
    id: str = field(default_factory=_new_event_id)
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class RunStarted(_TriageEventBase):
    message: str = ""


@dataclass(frozen=True)
class BatchCreated(_TriageEventBase):
    batch_id: int = 0
    segment: str = ""
    findings_count: int = 0
    message: str = ""


@dataclass(frozen=True)
class BatchStarted(_TriageEventBase):
    batch_id: int = 0
    segment: str = ""
    message: str = ""


@dataclass(frozen=True)
class BatchProgress(_TriageEventBase):
    batch_id: int = 0
    processed_count: int = 0
    total_count: int = 0
    message: str = ""


@dataclass(frozen=True)
class BatchCompleted(_TriageEventBase):
    batch_id: int = 0
    segment: str = ""
    findings_count: int = 0
    message: str = ""


@dataclass(frozen=True)
class BatchFailed(_TriageEventBase):
    batch_id: int = 0
    segment: str = ""
    message: str = ""
    error: str = ""


@dataclass(frozen=True)
class BatchRetry(_TriageEventBase):
    batch_id: int = 0
    attempt: int = 0
    message: str = ""


@dataclass(frozen=True)
class RunCompleted(_TriageEventBase):
    message: str = ""
    processed_count: int = 0


@dataclass(frozen=True)
class RunCancelled(_TriageEventBase):
    message: str = ""


type TriageEvent = (
    RunStarted
    | BatchCreated
    | BatchStarted
    | BatchProgress
    | BatchCompleted
    | BatchFailed
    | BatchRetry
    | RunCompleted
    | RunCancelled
)


_EVENT_TYPE_NAMES: dict[type, str] = {
    RunStarted: "run_started",
    BatchCreated: "batch_created",
    BatchStarted: "batch_started",
    BatchProgress: "batch_progress",
    BatchCompleted: "batch_completed",
    BatchFailed: "batch_failed",
    BatchRetry: "batch_retry",
    RunCompleted: "run_completed",
    RunCancelled: "run_cancelled",
}


def event_type_name(event: TriageEvent) -> str:
    """Return the SSE event_type string for *event* per endpoints.md §15.2."""
    return _EVENT_TYPE_NAMES[type(event)]
