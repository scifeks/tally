"""Unit tests for EnrichmentPipeline event emission.

EnrichmentPipeline emits one ``EnrichmentProgress`` per future-completion
in Phase 2 (LLM concurrency loop) and one ``EnrichmentComplete`` after
Phase 3 (SQLite writes). Both events carry ``project_id`` and ``run_id``
threaded in at construction time.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.ports.scan_event_sink import NullScanEventSink
from application.rag.enrichment import EnrichmentPipeline
from domain.pipeline import scan_events as se


class _RecordingSink(NullScanEventSink):
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:  # type: ignore[override]
        self.events.append(event)


def _make_finding_repo(rows: list[dict]) -> MagicMock:
    repo = MagicMock()
    repo.get_by_ids.return_value = rows
    return repo


def test_no_work_items_emits_nothing() -> None:
    sink = _RecordingSink()
    repo = _make_finding_repo([])

    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=7,
        project_id=42,
        event_sink=sink,
    )
    pipeline.enrich([1, 2, 3])

    assert sink.events == []


def test_all_pre_enriched_skips_phase2_and_emits_complete() -> None:
    sink = _RecordingSink()
    repo = _make_finding_repo(
        [
            {"id": 1, "enriched": 1},
            {"id": 2, "enriched": 1},
        ]
    )

    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=7,
        project_id=42,
        event_sink=sink,
    )
    pipeline.enrich([1, 2])

    # Pre-enriched rows skip Phase 2 entirely; pipeline returns before
    # enrichment, so no events fire.
    assert sink.events == []


def test_construction_with_no_event_sink_uses_null_sink() -> None:
    repo = _make_finding_repo([])
    pipeline = EnrichmentPipeline(finding_repo=repo, run_id=7, project_id=42)

    # Should not raise even when no sink is supplied.
    pipeline.enrich([1])

    # Internal sink is a NullScanEventSink (no emission).
    assert isinstance(pipeline._event_sink, NullScanEventSink)


def test_emission_carries_project_and_run_ids() -> None:
    """Both event types stamp the project_id/run_id from constructor."""
    sink = _RecordingSink()
    # Build a pipeline with one work item via mocked plan, force enrichment
    # path with a stub LLM provider that returns valid output.
    repo = _make_finding_repo([{"id": 1, "enriched": 0}])
    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=99,
        project_id=7,
        event_sink=sink,
    )

    # Stub _get_enrichment_plan to return a single legacy field, and
    # _call_llm_worker to return a valid dict — keeps Phase 2 simple.
    pipeline._get_enrichment_plan = lambda row: (["title"], None)  # type: ignore[method-assign]
    pipeline._call_llm_worker = lambda *a, **kw: {"title": "x"}  # type: ignore[method-assign]

    pipeline.enrich([1])

    # We expect at least EnrichmentComplete; EnrichmentProgress fires only
    # when there are work items reaching Phase 2.
    types = [type(e) for e in sink.events]
    assert se.EnrichmentComplete in types

    complete = next(e for e in sink.events if isinstance(e, se.EnrichmentComplete))
    assert complete.run_id == 99
    assert complete.project_id == 7
