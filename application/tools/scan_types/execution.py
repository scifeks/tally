"""Execution orchestration for scan-type strategy classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from application.tools.executor import ToolExecutor
from application.tools.registry import ToolRegistry
from application.tools.scan_types.models import ScanTypeConfig
from core.project_paths import ProjectPaths
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted
from domain.tools.base import ToolResult
from domain.tools.execution_config import NoirProviderSnapshot, ToolExecutionConfig
from domain.tools.interface import ExecutionContext, ToolInterface
from domain.tools.scan_types.models import SEGMENT_ORDER
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.tools.wrappers.utils.manifest_check import (
    has_manifests_for_language,
)

if TYPE_CHECKING:
    from core.config.manager import ConfigManager
    from core.config.schemas import Repository


def _build_tool_execution_config(
    config_manager: ConfigManager,
) -> ToolExecutionConfig:
    """Snapshot the slice of ConfigManager state that wrappers need."""
    gc = config_manager.global_config
    noir_snapshot: NoirProviderSnapshot | None = None
    noir_config = gc.noir_inference
    if noir_config is not None:
        provider_name = noir_config.provider
        provider_config = getattr(gc, provider_name, None)
        if provider_config is not None:
            base_url = getattr(provider_config, "base_url", None)
            model = getattr(provider_config, "model", None)
            num_ctx = getattr(provider_config, "num_ctx", None)
            if noir_config.model is not None:
                model = noir_config.model
            if noir_config.num_ctx is not None:
                num_ctx = noir_config.num_ctx
            if base_url and model:
                noir_snapshot = NoirProviderSnapshot(
                    base_url=base_url,
                    model=model,
                    num_ctx=num_ctx,
                )
    return ToolExecutionConfig(noir_provider=noir_snapshot)


def load_active_repos(base_path: str, project_name: str) -> list[Repository]:
    """Return active repos for the project, or ``[]`` if the DB is missing."""
    paths = ProjectPaths.from_canonical(base_path, project_name)
    if not paths.findings_db.exists():
        return []
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return RepositoryRepository(factory).list_active()


def should_skip_sca_tool(tool: Any, repo: Any) -> tuple[bool, str]:
    """Return (skip, reason) for an SCA tool that has no matching manifests.

    Returns (False, "") when the tool should proceed.  Returns (True, reason)
    when it should be skipped because no dependency manifest was found.
    """
    if not getattr(tool, "language_gates", None):
        return False, ""
    if getattr(tool, "scan_segment", "") != "sca":
        return False, ""
    if repo.path:
        mpath, mcontainer = repo.path, ""
    elif repo.docker_path and repo.container_name:
        mpath, mcontainer = repo.docker_path, repo.container_name
    else:
        return True, f"no manifest found for {repo.name}"
    has = any(
        has_manifests_for_language(mpath, lang, mcontainer)
        for lang in tool.language_gates
    )
    if not has:
        return True, f"no manifest found for {repo.name}"
    return False, ""


def make_context(
    tool_config: ToolExecutionConfig,
    project_name: str,
    base_path: str,
    registry: ToolRegistry,
    repo: Any,
    command_config: Any,
) -> ExecutionContext:
    return ExecutionContext(
        project_name=project_name,
        base_path=base_path,
        repo=repo,
        tool_config=tool_config,
        registry=registry,
        is_docker=(command_config.location == "docker" if command_config else False),
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
    if not config.prompt.confirm(f"  Run {tool.name}?"):
        return None
    if remaining_tools > 0:
        config.prompt.approve_all_remaining()

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
    """Order tool_set by SEGMENT_ORDER and discovery-first priority.

    Discovery tools (Katana, Noir) must run before downstream scanners
    (DalFox, XSStrike, ZAP) to produce output they can consume. Plain
    alphabetical sorting is insufficient because ``dalfox < katana``.
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
