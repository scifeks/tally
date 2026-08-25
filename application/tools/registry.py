import importlib
import inspect
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.tools.factory import ToolWrapperFactory
from core.config.schemas import CommandEntry, DockerContainer
from domain.tool_overrides.entry import ToolOverride
from domain.tools.base import ToolWrapper
from domain.tools.interface import ToolInterface

if TYPE_CHECKING:
    from application.ports.tool_overrides import ToolOverridesRepositoryPort

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _override_to_command_entry(override: ToolOverride) -> CommandEntry:
    container: DockerContainer | None = None
    if override.container_name and override.container_tool_path:
        container = DockerContainer(
            name=override.container_name,
            tool_path=override.container_tool_path,
        )
    return CommandEntry(
        type=override.type,
        location=override.location,
        path=override.path or "",
        container=container,
    )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._configs: dict[str, Any] = {}  # CommandEntry per tool
        self._service_overrides: list[ToolOverride] = []

    def register(self, tool: Any, config=None) -> None:
        self._tools[tool.name] = tool
        if config is not None:
            self._configs[tool.name] = config

    def clear(self) -> None:
        self._tools.clear()
        self._configs.clear()
        self._service_overrides.clear()

    def snapshot(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return (dict(self._tools), dict(self._configs))

    def restore(self, snapshot: tuple[dict[str, Any], dict[str, Any]]) -> None:
        tools, configs = snapshot
        self._tools.clear()
        self._tools.update(tools)
        self._configs.clear()
        self._configs.update(configs)

    def get_tool(self, name: str) -> Any | None:
        return self._tools.get(name)

    def get_tool_config(self, name: str):
        return self._configs.get(name)

    def resolve_tool_config(
        self,
        tool_name: str,
        repo_id: int | None = None,
        service_name: str | None = None,
    ):
        """Resolve tool config with service scope taking precedence over global.

        Returns the service-scoped override if repo_id and service_name are
        provided and a match exists, otherwise the global config, or None.
        """
        if repo_id is not None and service_name is not None:
            for o in self._service_overrides:
                if (
                    o.tool_name == tool_name
                    and o.repo_id == repo_id
                    and o.service_name == service_name
                ):
                    return _override_to_command_entry(o)
        return self._configs.get(tool_name)

    def get_service_path(self, tool_name: str, service, repo_path: str) -> str:
        config = self.get_tool_config(tool_name)
        if config is not None and config.location == "docker":
            return service.docker_path
        if service.relative_path:
            return str(Path(repo_path) / service.relative_path)
        return repo_path

    def get_tools_by_category(self, category: str) -> list[ToolWrapper]:
        return [t for t in self._tools.values() if t.category == category]

    def get_tools_by_scope(self, scope: str) -> list[ToolWrapper]:
        return [t for t in self._tools.values() if t.scope == scope]

    def get_all_tools(self) -> list[ToolWrapper]:
        return list(self._tools.values())

    def list_all(self) -> list[ToolWrapper]:
        return self.get_all_tools()

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def check_availability(self) -> dict[str, bool]:
        return {name: tool.check_available() for name, tool in self._tools.items()}


def discover_tools(
    registry: ToolRegistry,
    base_path: str = ".",
    project_name: str | None = None,
    overrides_repo: "ToolOverridesRepositoryPort | None" = None,
) -> None:
    """Populate registry with tool wrappers from commands.json or fallback to
    local discovery. Applies per-tool overrides from the repository when
    available to tailor execution to specific projects and services.
    """
    import json as _json

    registry.clear()

    wrappers_dir = _PROJECT_ROOT / "infrastructure" / "tools" / "wrappers"
    commands_path = Path(base_path) / "config" / "commands.json"

    commands_config = None
    if commands_path.exists():
        try:
            with open(commands_path) as f:
                data = _json.load(f)
            from core.config.schemas import CommandEntry

            commands_config = {
                name: CommandEntry(**entry) for name, entry in data.items()
            }
        except Exception as exc:
            logger.warning(
                "Failed to load commands.json (%s); falling back to local discovery",
                exc,
            )

    if commands_config is not None and project_name is not None:
        if overrides_repo is not None:
            rows, total = overrides_repo.list_paginated(offset=0, limit=10_000)
            if total > 10_000:
                raise RuntimeError(
                    f"tool_overrides has {total} rows; exceeds discover_tools ceiling"
                )
            for override in rows:
                if override.args_mode == "custom" and not override.path:
                    continue
                if override.scope == "service":
                    registry._service_overrides.append(override)
                else:
                    commands_config[override.tool_name] = _override_to_command_entry(
                        override
                    )

    if commands_config is not None:
        _discover_from_config(registry, commands_config, wrappers_dir)
    else:
        logger.warning(
            "commands.json not found at %s; running in fallback mode (all local tools)",
            commands_path,
        )
        _discover_fallback(registry, wrappers_dir)


def _discover_from_config(
    registry: ToolRegistry, commands_config, wrappers_dir: Path
) -> None:
    factory = ToolWrapperFactory()
    for tool_name, entry in commands_config.items():
        try:
            tool = factory.create(tool_name, entry)
            registry.register(tool, config=entry)
        except ImportError as exc:
            logger.warning("Skipping %r: import failed: %s", tool_name, exc)
        except Exception as exc:
            logger.warning("Skipping %r: instantiation failed: %s", tool_name, exc)


def _discover_fallback(registry: ToolRegistry, wrappers_dir: Path) -> None:
    local_dir = wrappers_dir / "local"
    for py_file in sorted(local_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"infrastructure.tools.wrappers.local.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue

        for _attr, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ToolInterface)
                and not inspect.isabstract(obj)
                and obj.__module__ == module_name
            ):
                try:
                    registry.register(obj())
                except TypeError:
                    pass


def register_burp_tool(
    registry: ToolRegistry,
    base_path: str,
) -> None:
    """Register Burp when configured and reachable."""
    from core.config.manager import ConfigManager
    from infrastructure.tools.burp.probe import (
        probe_burp_availability,
    )

    try:
        config = ConfigManager(base_path)
    except Exception:
        return

    burp_config = config.global_config.burp
    if burp_config is None:
        return

    available = probe_burp_availability(burp_config)
    if not available:
        return

    from infrastructure.tools.wrappers.burp import (
        BurpToolWrapper,
    )

    wrapper = BurpToolWrapper(burp_config=burp_config)
    registry.register(wrapper)
