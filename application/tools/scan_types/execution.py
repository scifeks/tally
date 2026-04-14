"""Execution orchestration for scan-type strategy classes."""

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


def make_context(
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


def execute_tool_passes(
    tool: ToolInterface,
    context: ExecutionContext,
    config: ScanTypeConfig,
    executor: ToolExecutor,
    remaining_tools: int = 0,
) -> ToolResult | None:
    """Prompt approval once, run all ExecutionPasses, return merged result."""
    if not config.auto_approve:
        try:
            answer = input(f"  Run {tool.name}? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer not in ("y", "yes"):
            return None
        if remaining_tools > 0:
            try:
                all_ans = input("    Approve all remaining? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
            else:
                if all_ans in ("y", "yes"):
                    config.auto_approve = True
                    if config.on_auto_approve:
                        config.on_auto_approve()

    passes = tool.build_execution_passes(context)
    if not passes:
        return None  # tool signaled skip via empty pass list
    pass_results = [executor.run(p, tool) for p in passes]
    return tool.merge_pass_results(pass_results)


def normalize_success(result: ToolResult, tool: ToolInterface) -> ToolResult:
    """Mark tools that exit non-zero on findings as successful when
    parsed_data is valid.
    """
    if tool.findings_exit_ok:
        if result.parsed_data and "error" not in result.parsed_data:
            result.success = True
    return result


def tools_for_segment(segment: str, registry: ToolRegistry) -> list[str]:
    """Return tool names registered under the given scan segment.

    Discovery tools (``is_discovery_tool=True``, e.g. Katana, Noir) are
    sorted before scanners so their output is available when downstream
    tools (DalFox, XSStrike, ZAP) start.  Matches the ordering applied
    by ``ordered_repo_tools``.
    """
    tools: list[Any] = registry.get_all_tools()
    segment_tools = [t for t in tools if t.scan_segment == segment]
    segment_tools.sort(key=lambda t: (not cast(Any, t).is_discovery_tool, t.name))
    return [t.name for t in segment_tools]


def dispatch_and_count_ingested(bus: EventBus, event: ToolCompleted) -> int:
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


def ordered_repo_tools(tool_set: set[str], registry: ToolRegistry) -> list[str]:
    """Order tool_set by SEGMENT_ORDER; within each segment, discovery tools
    run before scanners, then alphabetically within each group.

    Discovery tools (``is_discovery_tool=True``, e.g. Katana, Noir) must
    produce OAS3/JSONL output before scanners (DalFox, XSStrike, ZAP) can
    consume it.  A plain alphabetical sort is insufficient because
    ``dalfox < katana``, which would run DalFox before Katana on first scan.
    See ADR-00014.
    """
    result: list[str] = []
    for segment in SEGMENT_ORDER:
        tools_in_seg = [
            name
            for name in tool_set
            if registry.get_tool(name) is not None
            and cast(Any, registry.get_tool(name)).scan_segment == segment
        ]
        tools_in_seg.sort(
            key=lambda n: (
                not cast(Any, registry.get_tool(n)).is_discovery_tool,
                n,
            )
        )
        result.extend(tools_in_seg)
    return result
