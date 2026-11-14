"""Rich display adapter for the tool registry surface."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape as markup_escape
from rich.table import Table

from domain.tools.interface import TransportType

if TYPE_CHECKING:
    from application.tools.registry import ToolRegistry


def build_tool_table(tools, registry: ToolRegistry) -> Table:
    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("Tool", style="cyan", min_width=18)
    table.add_column("Category", min_width=10)
    table.add_column("Location", min_width=8)
    table.add_column("Status", min_width=14)
    table.add_column("Hint")

    for tool in tools:
        config = registry.get_tool_config(tool.name)
        transport = getattr(tool, "transport", TransportType.CLI)

        if transport == TransportType.HTTP:
            location = "http"
            avail = tool.check_available()
            if avail:
                status = "[green]v configured[/green]"
            else:
                status = "[yellow]! OFFLINE[/yellow]"
            hint = ""
        elif config and config.location == "docker":
            location = "docker"
            container = config.container.name if config else ""
            status = "[green]v configured[/green]"
            hint = f"Container: {container}"
        else:
            location = config.location if config else "local"
            avail = tool.check_available()
            version = tool.get_version() if avail else None
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


def print_discovery_summary(console: Console, registry: ToolRegistry) -> None:
    tools = registry.get_all_tools()
    available_count = sum(1 for t in tools if t.check_available())
    unavailable_count = len(tools) - available_count

    console.print("\n[bold]Configured Tools[/bold]")
    console.print(build_tool_table(tools, registry))

    summary = f"Loaded {len(tools)} tools ({available_count} available"
    if unavailable_count:
        summary += f", {unavailable_count} not installed"
    summary += ")"
    console.print(f"[bold]{summary}[/bold]")
