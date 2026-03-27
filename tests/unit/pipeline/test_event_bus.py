"""Unit tests for EventBus."""

from __future__ import annotations

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

    def test_unsubscribe_removes_handler(self) -> None:
        bus = EventBus()
        calls: list[object] = []
        handler = calls.append
        bus.subscribe(ToolCompleted, handler)
        bus.unsubscribe(ToolCompleted, handler)

        bus.dispatch(_tool_completed())

        assert calls == []

    def test_unsubscribe_only_removes_target_handler(self) -> None:
        bus = EventBus()
        calls_a: list[object] = []
        calls_b: list[object] = []
        handler_a = calls_a.append
        handler_b = calls_b.append
        bus.subscribe(ToolCompleted, handler_a)
        bus.subscribe(ToolCompleted, handler_b)
        bus.unsubscribe(ToolCompleted, handler_a)

        bus.dispatch(_tool_completed())

        assert calls_a == []  # handler_a was removed
        assert len(calls_b) == 1  # handler_b is unaffected

    def test_unsubscribe_is_idempotent(self) -> None:
        bus = EventBus()
        calls: list[object] = []
        handler = calls.append
        bus.subscribe(ToolCompleted, handler)
        bus.unsubscribe(ToolCompleted, handler)
        bus.unsubscribe(ToolCompleted, handler)  # second call must not raise

        bus.dispatch(_tool_completed())

        assert calls == []

    def test_unsubscribe_unknown_handler_does_not_raise(self) -> None:
        bus = EventBus()
        bus.unsubscribe(ToolCompleted, lambda e: None)  # never subscribed
