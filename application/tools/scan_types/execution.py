"""Execution orchestration for scan-type strategy classes."""

from __future__ import annotations

import logging
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
from infrastructure.tools.wrappers.docker._docker_exec import (
    build_docker_exec,
)
from infrastructure.tools.wrappers.utils.manifest_check import (
    has_manifests_for_language,
)

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.config.manager import ConfigManager
    from core.config.schemas import Repository


def _build_tool_execution_config(
    config_manager: ConfigManager,
) -> ToolExecutionConfig:
    """Snapshot the slice of ConfigManager state that wrappers need."""
    gc = config_manager.global_config
    noir_snapshot: NoirProviderSnapshot | None = None
    provider_name = gc.noir_provider
    if provider_name:
        provider_config = getattr(gc, provider_name, None)
        if provider_config is not None and hasattr(provider_config, "base_url"):
            noir_snapshot = NoirProviderSnapshot(
                base_url=provider_config.base_url,
                model=provider_config.model,
                num_ctx=getattr(provider_config, "num_ctx", None),
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


def _build_raw_command(
    tool_name: str,
    command_config: Any,
    cli_args: list[str],
) -> list[str]:
    """Build a command from raw CLI args using the tool's command config."""
    location = getattr(command_config, "location", None)
    if location == "docker":
        container = getattr(command_config, "container", None)
        if container is None:
            raise ValueError(
                f"Tool {tool_name!r}: docker location requires container config"
            )
        name = getattr(container, "name", None)
        tool_path = getattr(container, "tool_path", None)
        if not name or not tool_path:
            raise ValueError(f"Tool {tool_name!r}: container missing name or tool_path")
        return build_docker_exec(name, tool_path, cli_args)
    if location == "local":
        path = getattr(command_config, "path", None)
        if not path:
            raise ValueError(f"Tool {tool_name!r}: local location requires path")
        return [path, *cli_args]
    raise ValueError(f"Tool {tool_name!r}: unknown location {location!r}")


def execute_tool_passes(
    tool: ToolInterface,
    context: ExecutionContext,
    config: ScanTypeConfig,
    executor: ToolExecutor,
    remaining_tools: int = 0,
    command_config: Any = None,
) -> ToolResult | None:
    """Prompt approval once, run all ExecutionPasses, return merged result."""
    if not config.prompt.confirm(f"  Run {tool.name}?"):
        return None
    if remaining_tools > 0:
        config.prompt.approve_all_remaining()

    snapshot_json = config.arg_snapshots.get(tool.name)
    if snapshot_json is not None and command_config is not None:
        from domain.tool_arg_profiles.cli import snapshot_to_cli

        try:
            cli_args = snapshot_to_cli(snapshot_json)
        except ValueError:
            _log.exception(
                "Tool %s: invalid arg profile snapshot",
                tool.name,
            )
            cli_args = None
        if cli_args is not None:
            try:
                raw_cmd = _build_raw_command(tool.name, command_config, cli_args)
            except ValueError:
                _log.exception(
                    "Tool %s: failed to build raw command",
                    tool.name,
                )
                raw_cmd = None
            if raw_cmd is not None:
                _log.info(
                    "Tool %s: using custom arg profile",
                    tool.name,
                )
                return executor.run_raw(raw_cmd, tool)

    passes = tool.build_execution_passes(context)
    if not passes:
        return None
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
