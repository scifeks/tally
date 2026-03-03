import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console

from .base import ToolWrapper


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolWrapper] = {}

    def register(self, tool: ToolWrapper) -> None:
        self._tools[tool.name] = tool

    def clear(self) -> None:
        self._tools.clear()

    def get_tool(self, name: str) -> Optional[ToolWrapper]:
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> List[ToolWrapper]:
        return [t for t in self._tools.values() if t.category == category]

    def get_tools_by_scope(self, scope: str) -> List[ToolWrapper]:
        return [t for t in self._tools.values() if t.scope == scope]

    def get_all_tools(self) -> List[ToolWrapper]:
        return list(self._tools.values())

    def list_all(self) -> List[ToolWrapper]:
        return self.get_all_tools()

    def list_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def check_availability(self) -> Dict[str, bool]:
        return {name: tool.check_available() for name, tool in self._tools.items()}


tool_registry = ToolRegistry()


def discover_tools() -> None:
    """Scan core/tools/wrappers/ and register all ToolWrapper subclasses."""
    tool_registry.clear()

    wrappers_path = Path(__file__).parent / "wrappers"
    for py_file in sorted(wrappers_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"core.tools.wrappers.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue

        for _attr, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ToolWrapper)
                and obj is not ToolWrapper
                and obj.__module__ == module_name
            ):
                tool_registry.register(obj())


def print_discovery_summary(console: Console) -> None:
    """Print a Rich-formatted discovery summary."""
    tools = tool_registry.get_all_tools()
    available_count = sum(1 for t in tools if t.check_available())
    unavailable_count = len(tools) - available_count

    console.print("[bold]\\[*] Discovering tools...[/bold]")
    for tool in tools:
        avail = tool.check_available()
        marker = "[green]v[/green]" if avail else "[yellow]![/yellow]"
        status = "[green]available[/green]" if avail else "[yellow]NOT INSTALLED[/yellow]"
        console.print(
            f"  {marker} [cyan]{tool.name:<20}[/cyan]"
            f" [dim]{tool.category:<10}[/dim]"
            f" [dim]{tool.scope:<12}[/dim]"
            f" {status}"
        )

    summary = f"Loaded {len(tools)} tools ({available_count} available"
    if unavailable_count:
        summary += f", {unavailable_count} not installed"
    summary += ")"
    console.print(f"[bold]{summary}[/bold]")


# Auto-discover on import
discover_tools()
