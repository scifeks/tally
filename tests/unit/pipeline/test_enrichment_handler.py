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
    ids: list[int] | None = None,
    failed_tools: list[str] | None = None,
    run_id: int | None = 1,
) -> IngestCompleted:
    return IngestCompleted(
        ids=[1, 2] if ids is None else ids,
        failed_tools=[] if failed_tools is None else failed_tools,
        run_id=run_id,
        project_name="test-proj",
        base_path="/tmp",
    )


class TestEnrichmentHandler:
    def test_noop_when_ids_empty(self) -> None:
        bus = EventBus()
        received: list[EnrichmentCompleted] = []
        bus.subscribe(EnrichmentCompleted, received.append)

        handler = EnrichmentHandler(bus)
        handler.handle(_ingest_completed(ids=[]))

        assert received == []

    def test_dispatches_event_on_success(self) -> None:
        bus = EventBus()
        received: list[EnrichmentCompleted] = []
        bus.subscribe(EnrichmentCompleted, received.append)

        mock_repo = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.had_errors = False

        handler = EnrichmentHandler(bus)
        with (
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
        ):
            handler.handle(_ingest_completed(ids=[1]))

        assert len(received) == 1
        assert received[0].partial_success is False

    def test_dispatches_had_errors_true_on_partial_failure(self) -> None:
        bus = EventBus()
        received: list[EnrichmentCompleted] = []
        bus.subscribe(EnrichmentCompleted, received.append)

        mock_repo = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.had_errors = True

        handler = EnrichmentHandler(bus)
        with (
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.EnrichmentPipeline",
                return_value=mock_pipeline,
            ),
        ):
            handler.handle(_ingest_completed(ids=[1]))

        assert len(received) == 1
        assert received[0].partial_success is True

    def test_finding_repo_passed_to_pipeline(self) -> None:
        bus = EventBus()
        mock_repo = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.had_errors = False

        handler = EnrichmentHandler(bus)
        with (
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(MagicMock(), mock_repo, MagicMock(), MagicMock()),
            ),
            patch(
                "application.pipeline.handlers.EnrichmentPipeline",
                return_value=mock_pipeline,
            ) as mock_cls,
        ):
            handler.handle(_ingest_completed(ids=[1]))

        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs["finding_repo"] is mock_repo
