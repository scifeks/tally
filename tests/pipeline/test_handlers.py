"""Unit tests for core.pipeline EventBus and handlers.

All tests use stub EventBus interactions and mocked RAGEngine/FindingRepository —
no real ChromaDB or SQLite connections.

Run::

    python -m pytest tests/pipeline/ -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.pipeline.events import (
    EnrichmentCompleted,
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from core.pipeline.handlers import EnrichmentHandler, IngestHandler, PersistenceHandler
from domain.tools.base import ToolResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_result(
    tool_name: str = "semgrep",
    success: bool = True,
    parsed_data: dict | None = None,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=success,
        output="",
        parsed_data=parsed_data if parsed_data is not None else {"findings": []},
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


def _tool_completed(
    result: ToolResult | None = None,
    profile: str = "repo1",
    run_id: int | None = 1,
    project_name: str = "test-proj",
    base_path: str = "/tmp",
) -> ToolCompleted:
    return ToolCompleted(
        result=result or _make_tool_result(),
        profile=profile,
        run_id=run_id,
        project_name=project_name,
        base_path=base_path,
    )


def _ingest_completed(
    doc_ids: list[str] | None = None,
    failed_tools: list[str] | None = None,
    run_id: int | None = 1,
) -> IngestCompleted:
    return IngestCompleted(
        doc_ids=["doc1", "doc2"] if doc_ids is None else doc_ids,
        failed_tools=[] if failed_tools is None else failed_tools,
        run_id=run_id,
        project_name="test-proj",
        base_path="/tmp",
    )


def _enrich_completed(
    doc_ids: list[str] | None = None,
    partial_success: bool = True,
    run_id: int | None = 1,
) -> EnrichmentCompleted:
    return EnrichmentCompleted(
        doc_ids=doc_ids or ["doc1"],
        partial_success=partial_success,
        run_id=run_id,
        project_name="test-proj",
        base_path="/tmp",
    )


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------


class TestEventBus:
    def test_dispatch_calls_registered_handler(self) -> None:
        bus = EventBus()
        received: list[ToolCompleted] = []
        bus.subscribe(ToolCompleted, received.append)

        event = _tool_completed()
        bus.dispatch(event)

        assert received == [event]

    def test_dispatch_calls_all_registered_handlers(self) -> None:
        bus = EventBus()
        calls: list[str] = []
        bus.subscribe(ToolCompleted, lambda e: calls.append("h1"))
        bus.subscribe(ToolCompleted, lambda e: calls.append("h2"))

        bus.dispatch(_tool_completed())

        assert calls == ["h1", "h2"]

    def test_dispatch_does_not_call_other_type_handlers(self) -> None:
        bus = EventBus()
        called: list[bool] = []
        bus.subscribe(IngestCompleted, lambda e: called.append(True))

        bus.dispatch(_tool_completed())  # ToolCompleted, not IngestCompleted

        assert called == []

    def test_dispatch_multiple_event_types(self) -> None:
        bus = EventBus()
        tool_calls: list[object] = []
        ingest_calls: list[object] = []
        bus.subscribe(ToolCompleted, tool_calls.append)
        bus.subscribe(IngestCompleted, ingest_calls.append)

        tc = _tool_completed()
        ic = _ingest_completed()
        bus.dispatch(tc)
        bus.dispatch(ic)

        assert tool_calls == [tc]
        assert ingest_calls == [ic]


# ---------------------------------------------------------------------------
# IngestHandler tests
# ---------------------------------------------------------------------------


class TestIngestHandler:
    def test_dispatches_ingest_completed_on_rag_init_failure(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        with patch(
            "core.pipeline.handlers.IngestHandler._get_engine",
            side_effect=RuntimeError("chroma unavailable"),
        ):
            handler.handle(_tool_completed())

        assert len(received) == 1
        assert received[0].doc_ids == []
        assert received[0].failed_tools == []

    def test_dispatches_ingest_completed_with_failed_tool_on_exception(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        mock_engine = MagicMock()
        mock_ingestor = MagicMock()
        mock_ingestor.ingest_tool_output.side_effect = RuntimeError("ingest boom")

        handler = IngestHandler(bus)
        with (
            patch(
                "core.pipeline.handlers.IngestHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "core.pipeline.handlers.FindingIngestor",
                return_value=mock_ingestor,
            ),
        ):
            handler.handle(_tool_completed(result=_make_tool_result("semgrep")))

        assert len(received) == 1
        assert "semgrep" in received[0].failed_tools

    def test_skips_failed_result_and_dispatches_empty(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        failed_result = _make_tool_result(success=False)
        event = _tool_completed(result=failed_result)

        mock_engine = MagicMock()
        with patch(
            "core.pipeline.handlers.IngestHandler._get_engine",
            return_value=mock_engine,
        ):
            handler.handle(event)

        assert len(received) == 1
        assert received[0].doc_ids == []
        assert received[0].failed_tools == []

    def test_successful_ingest_dispatches_doc_ids(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        mock_engine = MagicMock()
        mock_ingestor = MagicMock()
        mock_ingestor.ingest_tool_output.return_value = ["id1", "id2"]

        handler = IngestHandler(bus)
        with (
            patch(
                "core.pipeline.handlers.IngestHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "core.pipeline.handlers.FindingIngestor",
                return_value=mock_ingestor,
            ),
        ):
            handler.handle(_tool_completed())

        assert len(received) == 1
        assert received[0].doc_ids == ["id1", "id2"]
        assert received[0].failed_tools == []


# ---------------------------------------------------------------------------
# EnrichmentHandler tests
# ---------------------------------------------------------------------------


class TestEnrichmentHandler:
    def test_noop_when_doc_ids_empty(self) -> None:
        bus = EventBus()
        received: list[EnrichmentCompleted] = []
        bus.subscribe(EnrichmentCompleted, received.append)

        handler = EnrichmentHandler(bus)
        handler.handle(_ingest_completed(doc_ids=[]))

        assert received == []

    def test_dispatches_partial_success_false_on_exception(self) -> None:
        bus = EventBus()
        received: list[EnrichmentCompleted] = []
        bus.subscribe(EnrichmentCompleted, received.append)

        mock_engine = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.enrich.side_effect = RuntimeError("llm down")

        handler = EnrichmentHandler(bus)
        with (
            patch(
                "core.pipeline.handlers.EnrichmentHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "core.pipeline.handlers.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
        ):
            handler.handle(_ingest_completed(doc_ids=["doc1"]))

        assert len(received) == 1
        assert received[0].partial_success is False

    def test_dispatches_partial_success_true_on_success(self) -> None:
        bus = EventBus()
        received: list[EnrichmentCompleted] = []
        bus.subscribe(EnrichmentCompleted, received.append)

        mock_engine = MagicMock()
        mock_pipeline = MagicMock()

        handler = EnrichmentHandler(bus)
        with (
            patch(
                "core.pipeline.handlers.EnrichmentHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "core.pipeline.handlers.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
        ):
            handler.handle(_ingest_completed(doc_ids=["doc1"]))

        assert len(received) == 1
        assert received[0].partial_success is True


# ---------------------------------------------------------------------------
# PersistenceHandler tests
# ---------------------------------------------------------------------------


class TestPersistenceHandler:
    def test_noop_when_run_id_is_none(self) -> None:
        bus = EventBus()
        mock_engine = MagicMock()
        mock_finding_repo = MagicMock()

        handler = PersistenceHandler(bus)
        with (
            patch(
                "core.pipeline.handlers.PersistenceHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "core.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
        ):
            handler.handle(_enrich_completed(run_id=None))

        mock_finding_repo.upsert_findings.assert_not_called()

    def test_calls_upsert_findings_with_fetched_metadata(self) -> None:
        bus = EventBus()

        mock_engine = MagicMock()
        mock_engine.get_document_by_id.side_effect = lambda doc_id: {
            "id": doc_id,
            "document": "text",
            "metadata": {"tool": "semgrep", "doc_id": doc_id},
        }
        mock_finding_repo = MagicMock()

        handler = PersistenceHandler(bus)
        with (
            patch(
                "core.pipeline.handlers.PersistenceHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "core.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_finding_repo, MagicMock(), MagicMock()),
            ),
        ):
            handler.handle(_enrich_completed(doc_ids=["doc1", "doc2"], run_id=42))

        mock_finding_repo.upsert_findings.assert_called_once_with(
            42,
            [
                {"tool": "semgrep", "doc_id": "doc1"},
                {"tool": "semgrep", "doc_id": "doc2"},
            ],
        )
