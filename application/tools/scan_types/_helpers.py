"""Intra-package utility helpers for scan-type strategy classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from application.tools.executor import ToolExecutor
from application.tools.registry import ToolRegistry
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ToolInterface
from domain.tools.scan_types.models import SEGMENT_ORDER, ScanTypeConfig

if TYPE_CHECKING:
    from core.config.manager import ConfigManager


def _make_context(
    config_manager: ConfigManager,
    project_name: str,
    base_path: str,
    registry: ToolRegistry,
    repo: Any,
    tool_config: Any,
) -> ExecutionContext:
    return ExecutionContext(
        project_name=project_name,
        base_path=base_path,
        repo=repo,
        config_manager=config_manager,
        registry=registry,
        is_docker=(tool_config.location == "docker" if tool_config else False),
        execution_mode="scan",
    )


def _execute_tool_passes(
    tool: ToolInterface,
    context: ExecutionContext,
    config: ScanTypeConfig,
    executor: ToolExecutor,
    remaining_tools: int = 0,
) -> ToolResult | None:
    """Prompt approval once, run all ExecutionPasses, return merged result."""
    if not config.auto_approve:
        try:
            answer = input(f"Run {tool.name}? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer not in ("y", "yes"):
            return None
        if remaining_tools > 0:
            try:
                all_ans = input("Approve all remaining? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
            else:
                if all_ans in ("y", "yes"):
                    config.auto_approve = True
                    if config.on_auto_approve:
                        config.on_auto_approve()

    passes = tool.build_execution_passes(context)
    pass_results = [executor.run(p, tool) for p in passes]
    return tool.merge_pass_results(pass_results)


def _normalize_success(result: ToolResult, tool: ToolInterface) -> ToolResult:
    """Mark tools that exit non-zero on findings as successful when
    parsed_data is valid.
    """
    if tool.findings_exit_ok:
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True
    return result


def _tools_for_segment(segment: str, registry: ToolRegistry) -> list[str]:
    """Return tool names registered under the given scan segment."""
    tools: list[Any] = registry.get_all_tools()
    return [t.name for t in tools if t.scan_segment == segment]


def _dispatch_and_count_ingested(bus: EventBus, event: ToolCompleted) -> int:
    """Dispatch a ToolCompleted event and return the number of findings ingested.

    Subscribes a one-shot counter to IngestCompleted before dispatching, then
    unsubscribes immediately after. Safe because EventBus is synchronous.
    """
    count = 0

    def _counter(e: IngestCompleted) -> None:
        nonlocal count
        count += len(e.ids)

    bus.subscribe(IngestCompleted, _counter)
    bus.dispatch(event)
    bus.unsubscribe(IngestCompleted, _counter)
    return count


def _ordered_repo_tools(tool_set: set[str], registry: ToolRegistry) -> list[str]:
    """Order tool_set by SEGMENT_ORDER, then alphabetically within each segment."""
    result: list[str] = []
    for segment in SEGMENT_ORDER:
        if segment == "network":
            continue
        tools_in_seg = sorted(
            name
            for name in tool_set
            if registry.get_tool(name) is not None
            and cast(Any, registry.get_tool(name)).scan_segment == segment
        )
        result.extend(tools_in_seg)
    return result
