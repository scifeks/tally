import importlib
import inspect
import logging
import re
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape as markup_escape
from rich.table import Table

from application.tools.factory import ToolWrapperFactory
from core.project_paths import ProjectPaths
from domain.tools.base import ToolWrapper
from domain.tools.interface import ToolInterface

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._configs: dict[str, Any] = {}  # CommandEntry per tool

    def register(self, tool: Any, config=None) -> None:
        self._tools[tool.name] = tool
        if config is not None:
            self._configs[tool.name] = config

    def clear(self) -> None:
        self._tools.clear()
        self._configs.clear()

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
        """Return the CommandEntry for a registered tool, or None."""
        return self._configs.get(name)

    def get_repo_path(self, tool_name: str, repo) -> str:
        """Return the correct filesystem path for tool execution.

        Uses repo.docker_path when the tool is configured for docker;
        falls back to repo.path for local tools or when no config exists.
        """
        config = self.get_tool_config(tool_name)
        if config is not None and config.location == "docker":
            return repo.docker_path
        return repo.path

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


tool_registry = ToolRegistry()


def discover_tools(base_path: str = ".", project_name: str | None = None) -> None:
    """Register tool wrappers, driven by commands.json when present.

    When commands.json exists at <base_path>/config/commands.json, only tools
    listed there are registered, using the wrapper from the configured location
    subdirectory (local/ or docker/).

    When commands.json is absent (pre-setup / development), all wrappers in
    wrappers/local/ are registered as a backward-compatible fallback.

    If project_name is provided and
    projects/<project_name>/config/commands.json exists, its entries overlay the
    global config (project entries fully replace global entries of the same name).
    """
    import json as _json

    tool_registry.clear()

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
                "Failed to load commands.json (%s) — falling back to local discovery",
                exc,
            )

    if commands_config is not None and project_name is not None:
        project_path = ProjectPaths.from_canonical(
            base_path, project_name
        ).commands_json
        if project_path.exists():
            try:
                with open(project_path) as f:
                    project_data = _json.load(f)
                from core.config.schemas import CommandEntry

                for name, entry in project_data.items():
                    commands_config[name] = CommandEntry(**entry)
            except Exception as exc:
                logger.warning("Failed to load project commands.json (%s)", exc)

    if commands_config is not None:
        _discover_from_config(commands_config, wrappers_dir)
    else:
        logger.warning(
            "commands.json not found at %s — "
            "running in fallback mode (all local tools)",
            commands_path,
        )
        _discover_fallback(wrappers_dir)


def _discover_from_config(commands_config, wrappers_dir: Path) -> None:
    """Register only tools listed in commands.json with their configured location."""
    factory = ToolWrapperFactory()
    for tool_name, entry in commands_config.items():
        try:
            tool = factory.create(tool_name, entry)
            tool_registry.register(tool, config=entry)
        except ImportError as exc:
            logger.warning("Skipping %r: import failed — %s", tool_name, exc)
        except Exception as exc:
            logger.warning("Skipping %r: instantiation failed — %s", tool_name, exc)


def _discover_fallback(wrappers_dir: Path) -> None:
    """Fallback: register all wrappers found in wrappers/local/."""
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
                tool_registry.register(obj())


def build_tool_table(tools, registry) -> Table:
    """Return a Rich Table of tool status rows (Tool/Category/Location/Status/Hint)."""
    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Tool", style="cyan", min_width=18)
    table.add_column("Category", min_width=10)
    table.add_column("Location", min_width=8)
    table.add_column("Status", min_width=14)
    table.add_column("Hint")

    for tool in tools:
        config = registry.get_tool_config(tool.name)
        location = config.location if config else "local"

        if location == "docker":
            container = config.container.name if config else ""
            status = "[green]v configured[/green]"
            hint = f"Container: {container}"
        else:
            avail = tool.check_available()
            version = tool.get_version() if avail else None
            # Extract bare version number from verbose strings like "semgrep 1.2.3"
            if version:
                match = re.search(r"\d+\.\d+[\d.]*", version)
                version = match.group(0) if match else version.split("(")[0].strip()
            if avail:
                safe = markup_escape(version) if version else "installed"
                status = f"[green]v {safe}[/green]"
            else:
                status = "[yellow]! NOT FOUND[/yellow]"
            hint = ""

        table.add_row(tool.name, tool.category, location, status, hint)

    return table


def print_discovery_summary(console: Console) -> None:
    """Print a Rich table summarising discovered tools."""
    tools = tool_registry.get_all_tools()
    available_count = sum(1 for t in tools if t.check_available())
    unavailable_count = len(tools) - available_count

    console.print("\n[bold]Configured Tools[/bold]")
    console.print(build_tool_table(tools, tool_registry))

    summary = f"Loaded {len(tools)} tools ({available_count} available"
    if unavailable_count:
        summary += f", {unavailable_count} not installed"
    summary += ")"
    console.print(f"[bold]{summary}[/bold]")


# Auto-discover on import
discover_tools()
