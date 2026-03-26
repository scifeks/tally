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


class TestIngestHandler:
    def test_dispatches_ingest_completed_when_no_handler_found(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        with patch(
            "application.pipeline.handlers.ToolHandlerFactory.load",
            return_value=None,
        ):
            handler.handle(_tool_completed())

        assert len(received) == 1
        assert received[0].ids == []
        assert received[0].failed_tools == []

    def test_dispatches_ingest_completed_with_failed_tool_on_exception(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        mock_handler = MagicMock()
        mock_handler.domain = "web"
        mock_handler.normalize.side_effect = RuntimeError("normalize boom")

        handler = IngestHandler(bus)
        with patch(
            "application.pipeline.handlers.ToolHandlerFactory.load",
            return_value=mock_handler,
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
        handler.handle(event)

        assert len(received) == 1
        assert received[0].ids == []
        assert received[0].failed_tools == []

    def test_successful_ingest_dispatches_sqlite_ids(self) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        mock_handler = MagicMock()
        mock_handler.domain = "web"
        mock_handler.normalize.return_value = [
            {"tool": "semgrep", "rule_id": "r1"},
            {"tool": "semgrep", "rule_id": "r2"},
        ]

        mock_finding_repo = MagicMock()
        mock_finding_repo.get_ids_by_fingerprints.return_value = [1, 2]

        handler = IngestHandler(bus)
        with (
            patch(
                "application.pipeline.handlers.ToolHandlerFactory.load",
                return_value=mock_handler,
            ),
            patch(
                "application.pipeline.handlers.make_store",
                return_value=(
                    MagicMock(),
                    mock_finding_repo,
                    MagicMock(),
                    MagicMock(),
                ),
            ),
        ):
            handler.handle(_tool_completed())

        assert len(received) == 1
        assert received[0].ids == [1, 2]
        assert received[0].failed_tools == []
