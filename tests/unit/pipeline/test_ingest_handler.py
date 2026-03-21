"""Unit tests for IngestHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.pipeline.handlers import IngestHandler
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted
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


class TestIngestHandler:
    def test_dispatches_ingest_completed_on_rag_init_failure(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        with patch(
            "application.pipeline.handlers.IngestHandler._get_engine",
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
                "application.pipeline.handlers.IngestHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.FindingIngestor",
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
            "application.pipeline.handlers.IngestHandler._get_engine",
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
                "application.pipeline.handlers.IngestHandler._get_engine",
                return_value=mock_engine,
            ),
            patch(
                "application.pipeline.handlers.FindingIngestor",
                return_value=mock_ingestor,
            ),
        ):
            handler.handle(_tool_completed())

        assert len(received) == 1
        assert received[0].doc_ids == ["id1", "id2"]
        assert received[0].failed_tools == []
