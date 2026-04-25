"""Report lifecycle events emitted by the report runner (Phase 7.3).

Domain-pure events (no transport concerns). The ``ReportEventSink`` port
(see ``application/ports/report_event_sink.py``) projects them into
either a no-op REPL discard or an async ``BusEvent`` publish for SSE
fan-out.

A "report run" is identified by ``report_id`` — the integer primary key
of the ``reports`` row. Field names match the SSE event payload
catalogue in ``docs/roadmap/ui-planning/API/endpoints.md §15.3`` so
adapters can do a straight projection.
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
class _ReportEventBase:
    report_id: int
    project_id: int | None
    id: str = field(default_factory=_new_event_id)
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class GenerationStarted(_ReportEventBase):
    format: str = ""
    message: str = ""


@dataclass(frozen=True)
class StepStarted(_ReportEventBase):
    step: str = ""
    message: str = ""


@dataclass(frozen=True)
class StepCompleted(_ReportEventBase):
    step: str = ""
    progress: int = 0
    message: str = ""


@dataclass(frozen=True)
class StepFailed(_ReportEventBase):
    step: str = ""
    message: str = ""
    error: str = ""


@dataclass(frozen=True)
class GenerationCompleted(_ReportEventBase):
    output_path: str = ""
    file_size_bytes: int = 0
    message: str = ""


@dataclass(frozen=True)
class GenerationFailed(_ReportEventBase):
    error: str = ""
    message: str = ""


@dataclass(frozen=True)
class GenerationCancelled(_ReportEventBase):
    message: str = ""


type ReportEvent = (
    GenerationStarted
    | StepStarted
    | StepCompleted
    | StepFailed
    | GenerationCompleted
    | GenerationFailed
    | GenerationCancelled
)


_EVENT_TYPE_NAMES: dict[type, str] = {
    GenerationStarted: "generation_started",
    StepStarted: "step_started",
    StepCompleted: "step_completed",
    StepFailed: "step_failed",
    GenerationCompleted: "generation_completed",
    GenerationFailed: "generation_failed",
    GenerationCancelled: "generation_cancelled",
}


def event_type_name(event: ReportEvent) -> str:
    """Return the SSE event_type string for *event* per endpoints.md §15.3."""
    return _EVENT_TYPE_NAMES[type(event)]
