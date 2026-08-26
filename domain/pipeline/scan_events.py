"""Scan lifecycle events emitted by the orchestrator.

Events are domain-pure and carry no transport concerns. The
``ScanEventSink`` port converts them to Rich console output (REPL) or
async SSE publishes (web).
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
class _ScanEventBase:
    run_id: int
    project_id: int | None
    id: str = field(default_factory=_new_event_id)
    timestamp: str = field(default_factory=_utc_now)


@dataclass(frozen=True)
class RunStarted(_ScanEventBase):
    message: str = ""


@dataclass(frozen=True)
class SegmentStarted(_ScanEventBase):
    segment: str = ""
    message: str = ""


@dataclass(frozen=True)
class ToolStarted(_ScanEventBase):
    segment: str = ""
    repo: str = ""
    tool: str = ""
    message: str = ""


@dataclass(frozen=True)
class ToolSkipped(_ScanEventBase):
    segment: str = ""
    repo: str = ""
    tool: str = ""
    message: str = ""
    skip_reason: str = ""


@dataclass(frozen=True)
class ToolCompleted(_ScanEventBase):
    segment: str = ""
    repo: str = ""
    tool: str = ""
    message: str = ""
    findings_count: int = 0
    duration: float = 0.0
    exit_code: int = 0


@dataclass(frozen=True)
class ToolProgress(_ScanEventBase):
    segment: str = ""
    repo: str = ""
    tool: str = ""
    message: str = ""
    status: str = ""
    findings_count: int = 0
    progress_pct: int = 0


@dataclass(frozen=True)
class ToolFailed(_ScanEventBase):
    segment: str = ""
    repo: str = ""
    tool: str = ""
    message: str = ""
    exit_code: int = 0
    duration: float = 0.0


@dataclass(frozen=True)
class EnrichmentProgress(_ScanEventBase):
    message: str = ""
    enriched_count: int = 0
    total_to_enrich: int = 0


@dataclass(frozen=True)
class EnrichmentComplete(_ScanEventBase):
    message: str = ""
    enriched_count: int = 0


@dataclass(frozen=True)
class SegmentCompleted(_ScanEventBase):
    segment: str = ""
    message: str = ""
    findings_count: int = 0


@dataclass(frozen=True)
class RunCompleted(_ScanEventBase):
    message: str = ""
    findings_count: int = 0


@dataclass(frozen=True)
class RunCancelled(_ScanEventBase):
    message: str = ""


@dataclass(frozen=True)
class RunFailed(_ScanEventBase):
    message: str = ""


type ScanEvent = (
    RunStarted
    | SegmentStarted
    | ToolStarted
    | ToolSkipped
    | ToolCompleted
    | ToolProgress
    | ToolFailed
    | EnrichmentProgress
    | EnrichmentComplete
    | SegmentCompleted
    | RunCompleted
    | RunCancelled
    | RunFailed
)


_EVENT_TYPE_NAMES: dict[type, str] = {
    RunStarted: "run_started",
    SegmentStarted: "segment_started",
    ToolStarted: "tool_started",
    ToolSkipped: "tool_skipped",
    ToolCompleted: "tool_completed",
    ToolProgress: "tool_progress",
    ToolFailed: "tool_failed",
    EnrichmentProgress: "enrichment_progress",
    EnrichmentComplete: "enrichment_complete",
    SegmentCompleted: "segment_completed",
    RunCompleted: "run_completed",
    RunCancelled: "run_cancelled",
    RunFailed: "run_failed",
}


def event_type_name(event: ScanEvent) -> str:
    """Return the SSE event_type string for *event*."""
    return _EVENT_TYPE_NAMES[type(event)]
