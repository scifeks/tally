"""Tests for the Phase 5.1 scan event types."""

from __future__ import annotations

import re

from domain.pipeline import scan_events as se

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_run_started_defaults_id_and_timestamp() -> None:
    e = se.RunStarted(run_id=7, project_id=3)
    assert e.run_id == 7
    assert e.project_id == 3
    assert _UUID4_RE.match(e.id)
    assert "T" in e.timestamp  # ISO-8601 with time component


def test_event_type_name_round_trip() -> None:
    cases = [
        (se.RunStarted(run_id=1, project_id=1), "run_started"),
        (se.SegmentStarted(run_id=1, project_id=1), "segment_started"),
        (se.ToolStarted(run_id=1, project_id=1), "tool_started"),
        (se.ToolSkipped(run_id=1, project_id=1), "tool_skipped"),
        (se.ToolCompleted(run_id=1, project_id=1), "tool_completed"),
        (se.ToolFailed(run_id=1, project_id=1), "tool_failed"),
        (
            se.EnrichmentProgress(run_id=1, project_id=1),
            "enrichment_progress",
        ),
        (
            se.EnrichmentComplete(run_id=1, project_id=1),
            "enrichment_complete",
        ),
        (se.SegmentCompleted(run_id=1, project_id=1), "segment_completed"),
        (se.RunCompleted(run_id=1, project_id=1), "run_completed"),
        (se.RunCancelled(run_id=1, project_id=1), "run_cancelled"),
        (se.RunFailed(run_id=1, project_id=1), "run_failed"),
    ]
    for event, name in cases:
        assert se.event_type_name(event) == name


def test_tool_completed_carries_payload_fields() -> None:
    e = se.ToolCompleted(
        run_id=1,
        project_id=2,
        segment="code",
        repo="dvwa",
        tool="gitleaks",
        message="done",
        findings_count=4,
        duration=1.5,
        exit_code=0,
    )
    assert e.findings_count == 4
    assert e.duration == 1.5
    assert e.exit_code == 0
    assert e.tool == "gitleaks"


def test_events_are_frozen() -> None:
    e = se.RunStarted(run_id=1, project_id=1)
    try:
        e.run_id = 2  # type: ignore[misc]
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("scan event should be frozen")
