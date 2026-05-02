"""Report lifecycle events.

Domain-pure events (no transport concerns). The ``ReportEventSink`` port
projects them into either a REPL discard or an async ``BusEvent`` for
SSE fan-out. A report run is identified by ``report_id`` (the primary
key of the ``reports`` row).
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


@dataclass(frozen=True)
class DraftStarted(_ReportEventBase):
    section: str = ""
    message: str = ""


@dataclass(frozen=True)
class DraftCompleted(_ReportEventBase):
    section: str = ""
    output_path: str = ""
    file_size_bytes: int = 0
    word_count: int = 0
    message: str = ""


@dataclass(frozen=True)
class DraftFailed(_ReportEventBase):
    section: str = ""
    error: str = ""
    message: str = ""


type ReportEvent = (
    GenerationStarted
    | StepStarted
    | StepCompleted
    | StepFailed
    | GenerationCompleted
    | GenerationFailed
    | GenerationCancelled
    | DraftStarted
    | DraftCompleted
    | DraftFailed
)

type DraftEvent = DraftStarted | DraftCompleted | DraftFailed


_EVENT_TYPE_NAMES: dict[type, str] = {
    GenerationStarted: "generation_started",
    StepStarted: "step_started",
    StepCompleted: "step_completed",
    StepFailed: "step_failed",
    GenerationCompleted: "generation_completed",
    GenerationFailed: "generation_failed",
    GenerationCancelled: "generation_cancelled",
    DraftStarted: "draft_started",
    DraftCompleted: "draft_completed",
    DraftFailed: "draft_failed",
}


def event_type_name(event: ReportEvent) -> str:
    """Return the SSE event_type string for *event* per endpoints.md §15.3."""
    return _EVENT_TYPE_NAMES[type(event)]
