"""Unit tests for EnrichmentHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.handlers import EnrichmentHandler
from domain.pipeline.events import EnrichmentCompleted, EventBus, IngestCompleted
from domain.tools.base import ToolResult


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
                "application.pipeline.handlers.EnrichmentHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.EnrichmentPipeline",
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
                "application.pipeline.handlers.EnrichmentHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
        ):
            handler.handle(_ingest_completed(doc_ids=["doc1"]))

        assert len(received) == 1
        assert received[0].partial_success is True
