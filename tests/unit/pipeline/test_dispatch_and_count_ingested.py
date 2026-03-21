"""Unit tests for _dispatch_and_count_ingested."""

from __future__ import annotations

from application.tools.scan_types._helpers import _dispatch_and_count_ingested
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


class TestDispatchAndCountIngested:
    """_dispatch_and_count_ingested returns the total doc_ids emitted via
    IngestCompleted and cleans up its internal counter handler afterward."""

    def _make_ingest_subscriber(self, bus: EventBus, doc_ids: list[str]) -> None:
        """Register a ToolCompleted handler that immediately emits IngestCompleted."""

        def _emit(event: ToolCompleted) -> None:
            bus.dispatch(
                IngestCompleted(
                    doc_ids=doc_ids,
                    failed_tools=[],
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )

        bus.subscribe(ToolCompleted, _emit)

    def test_returns_zero_when_no_ingest_completed_emitted(self) -> None:
        bus = EventBus()
        # No subscriber emits IngestCompleted, so count must be 0.
        count = _dispatch_and_count_ingested(bus, _tool_completed())
        assert count == 0

    def test_returns_doc_id_count_on_successful_ingest(self) -> None:
        bus = EventBus()
        self._make_ingest_subscriber(bus, ["id1", "id2", "id3"])

        count = _dispatch_and_count_ingested(bus, _tool_completed())

        assert count == 3

    def test_counter_is_removed_after_dispatch(self) -> None:
        """The one-shot counter must not accumulate across multiple calls."""
        bus = EventBus()
        self._make_ingest_subscriber(bus, ["id1", "id2"])

        first = _dispatch_and_count_ingested(bus, _tool_completed())
        second = _dispatch_and_count_ingested(bus, _tool_completed())

        assert first == 2
        assert second == 2  # not 4

    def test_returns_zero_for_empty_doc_ids(self) -> None:
        bus = EventBus()
        self._make_ingest_subscriber(bus, [])

        count = _dispatch_and_count_ingested(bus, _tool_completed())

        assert count == 0
