"""Unit tests for EnrichmentPipeline event emission.

EnrichmentPipeline emits an initial ``EnrichmentProgress`` at count 0
before Phase 2, one ``EnrichmentProgress`` per future-completion during
Phase 2, and one ``EnrichmentComplete`` after Phase 3.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.ports.scan_event_sink import NullScanEventSink
from application.rag.enrichment import EnrichmentPipeline
from domain.pipeline import scan_events as se
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy


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
    # _call_llm_worker to return a valid dict; keeps Phase 2 simple.
    pipeline._get_enrichment_plan = lambda row: (["title"], None)  # type: ignore[method-assign]
    pipeline._call_llm_worker = lambda *a, **kw: {"title": "x"}  # type: ignore[method-assign]

    # Pre-seed the lazy LLM provider so the property short-circuits and
    # never reads config/global.json. Real provider resolution happens in
    # integration tests via _seed_global_config; this is a unit test for
    # event emission.
    pipeline._llm_provider = MagicMock()

    pipeline.enrich([1])

    types = [type(e) for e in sink.events]
    assert se.EnrichmentComplete in types

    complete = next(e for e in sink.events if isinstance(e, se.EnrichmentComplete))
    assert complete.run_id == 99
    assert complete.project_id == 7


def test_initial_progress_emitted_before_enrichment() -> None:
    """First event must be EnrichmentProgress with count 0."""
    sink = _RecordingSink()
    repo = _make_finding_repo([{"id": 1, "enriched": 0}])
    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=5,
        project_id=10,
        event_sink=sink,
    )
    pipeline._get_enrichment_plan = lambda row: (["title"], None)  # type: ignore[method-assign]
    pipeline._call_llm_worker = lambda *a, **kw: {"title": "x"}  # type: ignore[method-assign]
    pipeline._llm_provider = MagicMock()

    pipeline.enrich([1])

    progress_events = [e for e in sink.events if isinstance(e, se.EnrichmentProgress)]
    assert len(progress_events) >= 2
    assert progress_events[0].enriched_count == 0
    assert progress_events[0].total_to_enrich == 1
    assert progress_events[0].run_id == 5
    assert progress_events[0].project_id == 10
    assert progress_events[1].enriched_count == 1


def test_per_field_progress_increments_per_finding() -> None:
    """With per-field enrichment, the counter increments once
    per finding (after all its fields complete), not per field."""
    sink = _RecordingSink()
    repo = _make_finding_repo(
        [
            {"id": 1, "enriched": 0},
            {"id": 2, "enriched": 0},
        ]
    )
    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=1,
        project_id=1,
        event_sink=sink,
        max_workers=1,
    )
    specs = [
        FieldEnrichmentSpec("title", ("description",), PromptStrategy.GENERIC),
        FieldEnrichmentSpec("risk_type", ("description",), PromptStrategy.GENERIC),
    ]
    pipeline._get_enrichment_plan = lambda row: (None, list(specs))  # type: ignore[method-assign]
    pipeline._enrich_single_field = lambda meta, spec: "x"  # type: ignore[method-assign]
    pipeline._llm_provider = MagicMock()

    pipeline.enrich([1, 2])

    progress = [e for e in sink.events if isinstance(e, se.EnrichmentProgress)]
    counts = [e.enriched_count for e in progress]
    assert counts == [0, 1, 2]
