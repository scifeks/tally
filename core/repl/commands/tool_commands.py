"""Tool management commands for the tally REPL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.repl.interface import REPL


class ToolCommands:
    """Handlers for tool configuration management commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Top-level dispatcher
    # ------------------------------------------------------------------

    def cmd_tool(self, _cmd: str, args: list) -> None:
        """tool [add|edit <name>|remove <name>|list] — manage tool configuration."""
        if not args:
            self.repl._cmd_help_scoped("tool")
            return

        sub = args[0].lower()
        if sub == "list":
            self._cmd_tool_list()
        elif sub == "add":
            self._cmd_tool_add()
        elif sub == "edit":
            if len(args) < 2:
                self.repl.console.print("[red]Usage:[/red] tool edit <name>")
                return
            self._cmd_tool_edit(args[1])
        elif sub == "remove":
            if len(args) < 2:
                self.repl.console.print("[red]Usage:[/red] tool remove <name>")
                return
            self._cmd_tool_remove(args[1])
        else:
            self.repl.console.print(f"[red]Unknown subcommand:[/red] {sub}")
            self.repl._cmd_help_scoped("tool")

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    def _cmd_tool_list(self) -> None:
        from core.tools.registry import build_tool_table, tool_registry

        tools = tool_registry.get_all_tools()
        if not tools:
            self.repl.console.print(
                "[dim]No tools configured. "
                "Use [bold]tool add[/bold] to add a tool.[/dim]"
            )
            return
        self.repl.console.print(build_tool_table(tools, tool_registry))

    def _cmd_tool_add(self) -> None:
        from core.setup.commands_setup import interview_tool

        local_tools, docker_tools = self._get_wrapper_availability()
        all_available = sorted(local_tools | docker_tools)

        commands = self._load_commands_json()
        configured = set(commands.keys())
        unconfigured = [t for t in all_available if t not in configured]

        if not unconfigured:
            self.repl.console.print(
                "[dim]All available tools are already configured.[/dim]"
            )
            return

        self.repl.console.print("\nAvailable tools to add:")
        for i, name in enumerate(unconfigured, 1):
            badges = []
            if name in local_tools:
                badges.append("local")
            if name in docker_tools:
                badges.append("docker")
            self.repl.console.print(f"  {i}. {name}  ({'/'.join(badges)})")

        raw = input("\nEnter tool name (or number): ").strip()
        if not raw:
            return

        if raw.isdigit():
            idx = int(raw) - 1
            if idx < 0 or idx >= len(unconfigured):
                self.repl.console.print("[red]Invalid selection.[/red]")
                return
            tool_name = unconfigured[idx]
        else:
            tool_name = raw

        if tool_name not in (local_tools | docker_tools):
            self.repl.console.print(f"[red]No wrapper found for:[/red] {tool_name}")
            return
        if tool_name in configured:
            self.repl.console.print(f"[red]Tool already configured:[/red] {tool_name}")
            return

        has_local = tool_name in local_tools
        has_docker = tool_name in docker_tools
        entry = interview_tool(tool_name, has_local, has_docker)

        if entry is None:
            return

        commands[tool_name] = entry
        self._save_commands_json(commands)
        self._reload_registry()
        self.repl.console.print(f"[green]Tool added:[/green] {tool_name}")

        if tool_name == "nmap":
            if not self.repl.active_project:
                self.repl.console.print(
                    "[yellow]No active project. "
                    "Use 'project add' or 'project switch <name>'[/yellow]"
                )
            else:
                from core.setup.nmap_setup import interview_nmap_config

                interview_nmap_config(self.repl.active_project, self.repl.base_path)

    def _cmd_tool_edit(self, tool_name: str) -> None:
        from core.setup.commands_setup import interview_tool

        commands = self._load_commands_json()
        if tool_name not in commands:
            names = ", ".join(sorted(commands.keys()))
            self.repl.console.print(f"[red]Tool not configured:[/red] {tool_name}")
            self.repl.console.print(f"Configured tools: {names}")
            return

        local_tools, docker_tools = self._get_wrapper_availability()
        has_local = tool_name in local_tools
        has_docker = tool_name in docker_tools

        entry = interview_tool(
            tool_name, has_local, has_docker, defaults=commands[tool_name]
        )

        if entry is None:
            self.repl.console.print("Cancelled.")
            return

        commands[tool_name] = entry
        self._save_commands_json(commands)
        self._reload_registry()
        self.repl.console.print(f"[green]Tool updated:[/green] {tool_name}")

        if tool_name == "nmap":
            if not self.repl.active_project:
                self.repl.console.print(
                    "[yellow]No active project. "
                    "Use 'project add' or 'project switch <name>'[/yellow]"
                )
            else:
                from core.config.manager import ConfigManager
                from core.setup.nmap_setup import interview_nmap_config

                existing = ConfigManager(self.repl.base_path).load_nmap_hosts(
                    self.repl.active_project
                )
                interview_nmap_config(
                    self.repl.active_project, self.repl.base_path, existing=existing
                )

    def _cmd_tool_remove(self, tool_name: str) -> None:
        commands = self._load_commands_json()
        if tool_name not in commands:
            names = ", ".join(sorted(commands.keys()))
            self.repl.console.print(f"[red]Tool not configured:[/red] {tool_name}")
            self.repl.console.print(f"Configured tools: {names}")
            return

        raw = (
            input(f"  Remove tool '{tool_name}'? This cannot be undone. [y/N]: ")
            .strip()
            .lower()
        )
        if raw not in ("y", "yes"):
            self.repl.console.print("Cancelled.")
            return

        del commands[tool_name]
        self._save_commands_json(commands)
        self._reload_registry()
        self.repl.console.print(f"[green]Tool removed:[/green] {tool_name}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _commands_json_path(self) -> Path:
        return Path(self.repl.base_path) / "config" / "commands.json"

    def _load_commands_json(self) -> dict:
        path = self._commands_json_path()
        if not path.exists():
            return {}
        with open(path) as f:
            return json.load(f)

    def _save_commands_json(self, commands: dict) -> None:
        path = self._commands_json_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(commands, f, indent=2)

    def _reload_registry(self) -> None:
        from core.tools.registry import discover_tools

        discover_tools(self.repl.base_path)

    def _get_wrapper_availability(self) -> tuple:
        wrappers_dir = Path(__file__).parent.parent.parent / "tools" / "wrappers"
        local_dir = wrappers_dir / "local"
        docker_dir = wrappers_dir / "docker"
        local_tools = {
            f.stem.replace("_", "-")
            for f in local_dir.glob("*.py")
            if not f.name.startswith("_")
        }
        docker_tools = {
            f.stem.replace("_", "-")
            for f in docker_dir.glob("*.py")
            if not f.name.startswith("_")
        }
        return local_tools, docker_tools
