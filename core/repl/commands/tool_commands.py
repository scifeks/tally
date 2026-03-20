"""Tool management commands for the tally REPL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.repl.help_renderer import HelpRenderer
    from core.repl.interface import REPL


class ToolCommands:
    """Handlers for tool configuration management commands."""

    def __init__(self, repl: REPL, help_renderer: HelpRenderer) -> None:
        self.repl = repl
        self.help_renderer = help_renderer

    # ------------------------------------------------------------------
    # Top-level dispatcher
    # ------------------------------------------------------------------

    def cmd_tool(self, _cmd: str, args: list) -> None:
        """tool [add|edit <name>|remove <name>|list] — manage tool configuration."""
        if not args:
            self.help_renderer.render("tool")
            return

        project_name, args = self._parse_project_flag(args)

        sub = args[0].lower() if args else ""

        if project_name is not None:
            if not self._validate_project_arg(project_name):
                return
            if sub == "list":
                self._cmd_tool_list_project(project_name)
            elif sub == "add":
                self._cmd_tool_add_project(project_name)
            elif sub == "edit":
                if len(args) < 2:
                    self.repl.console.print(
                        "[red]Usage:[/red] tool edit <name> --project=<name>"
                    )
                    return
                self._cmd_tool_edit_project(args[1], project_name)
            elif sub == "remove":
                if len(args) < 2:
                    self.repl.console.print(
                        "[red]Usage:[/red] tool remove <name> --project=<name>"
                    )
                    return
                self._cmd_tool_remove_project(args[1], project_name)
            else:
                self.repl.console.print(f"[red]Unknown subcommand:[/red] {sub}")
                self.help_renderer.render("tool")
            return

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
            self.help_renderer.render("tool")

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    def _cmd_tool_list(self) -> None:
        from application.tools.registry import build_tool_table, tool_registry

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
        from application.tools.registry import discover_tools

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

    # ------------------------------------------------------------------
    # Project flag helpers
    # ------------------------------------------------------------------

    def _parse_project_flag(self, args: list) -> tuple[str | None, list]:
        """Extract --project=<name> from args. Returns (project_name, remaining)."""
        for i, arg in enumerate(args):
            if isinstance(arg, str) and arg.startswith("--project="):
                return arg[10:], args[:i] + args[i + 1 :]
        return None, args

    def _validate_project_arg(self, project_name: str) -> bool:
        if not self.repl.active_project:
            self.repl.console.print(
                "[red]No active project.[/red] "
                "Use 'project add' or 'project switch <name>' "
                "before using --project."
            )
            return False
        config_path = (
            Path(self.repl.base_path)
            / "projects"
            / project_name
            / "config"
            / "project.json"
        )
        if not config_path.exists():
            self.repl.console.print(f"[red]Project not found:[/red] {project_name}")
            return False
        return True

    # ------------------------------------------------------------------
    # Project-level file helpers
    # ------------------------------------------------------------------

    def _project_commands_json_path(self, project_name: str) -> Path:
        return (
            Path(self.repl.base_path)
            / "projects"
            / project_name
            / "config"
            / "commands.json"
        )

    def _load_project_commands_json(self, project_name: str) -> dict:
        path = self._project_commands_json_path(project_name)
        if not path.exists():
            return {}
        with open(path) as f:
            return json.load(f)

    def _save_project_commands_json(self, project_name: str, commands: dict) -> None:
        path = self._project_commands_json_path(project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(commands, f, indent=2)

    # ------------------------------------------------------------------
    # Project-scoped subcommands
    # ------------------------------------------------------------------

    def _cmd_tool_list_project(self, project_name: str) -> None:
        from rich.table import Table

        commands = self._load_project_commands_json(project_name)
        if not commands:
            self.repl.console.print(
                f"[dim]No project-level tool overrides configured "
                f"for '{project_name}'.[/dim]"
            )
            return

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("Tool", style="cyan", min_width=18)
        table.add_column("Type", min_width=8)
        table.add_column("Location", min_width=8)
        table.add_column("Path or Container")

        for name, entry in sorted(commands.items()):
            location = entry.get("location", "")
            tool_type = entry.get("type", "")
            if location == "docker":
                container = entry.get("container", {})
                detail = f"{container.get('name', '')}:{container.get('tool_path', '')}"
            else:
                detail = entry.get("path", "")
            table.add_row(name, tool_type, location, detail)

        self.repl.console.print(table)

    def _cmd_tool_add_project(self, project_name: str) -> None:
        from core.setup.commands_setup import interview_tool

        local_tools, docker_tools = self._get_wrapper_availability()
        all_available = sorted(local_tools | docker_tools)

        project_commands = self._load_project_commands_json(project_name)
        project_configured = set(project_commands.keys())
        unconfigured = [t for t in all_available if t not in project_configured]

        global_commands = self._load_commands_json()

        if not unconfigured:
            self.repl.console.print(
                "[dim]All available tools are already configured "
                f"at the project level for '{project_name}'.[/dim]"
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
        if tool_name in project_configured:
            self.repl.console.print(f"[red]Tool already configured:[/red] {tool_name}")
            return

        if tool_name in global_commands:
            self.repl.console.print(
                f"[yellow]Warning:[/yellow] '{tool_name}' is already configured "
                f"globally. You are creating a project-level override for "
                f"project '{project_name}'."
            )

        has_local = tool_name in local_tools
        has_docker = tool_name in docker_tools
        entry = interview_tool(tool_name, has_local, has_docker)

        if entry is None:
            return

        project_commands[tool_name] = entry
        self._save_project_commands_json(project_name, project_commands)
        self.repl.console.print(f"[green]Tool added:[/green] {tool_name}")

        if tool_name == "nmap":
            from core.setup.nmap_setup import interview_nmap_config

            interview_nmap_config(project_name, self.repl.base_path)

    def _cmd_tool_edit_project(self, tool_name: str, project_name: str) -> None:
        from core.setup.commands_setup import interview_tool

        project_commands = self._load_project_commands_json(project_name)
        if tool_name not in project_commands:
            names = ", ".join(sorted(project_commands.keys()))
            self.repl.console.print(f"[red]Tool not configured:[/red] {tool_name}")
            self.repl.console.print(f"Project-configured tools: {names or 'none'}")
            return

        local_tools, docker_tools = self._get_wrapper_availability()
        has_local = tool_name in local_tools
        has_docker = tool_name in docker_tools

        entry = interview_tool(
            tool_name,
            has_local,
            has_docker,
            defaults=project_commands[tool_name],
        )

        if entry is None:
            self.repl.console.print("Cancelled.")
            return

        project_commands[tool_name] = entry
        self._save_project_commands_json(project_name, project_commands)
        self.repl.console.print(f"[green]Tool updated:[/green] {tool_name}")

    def _cmd_tool_remove_project(self, tool_name: str, project_name: str) -> None:
        project_commands = self._load_project_commands_json(project_name)
        if tool_name not in project_commands:
            names = ", ".join(sorted(project_commands.keys()))
            self.repl.console.print(f"[red]Tool not configured:[/red] {tool_name}")
            self.repl.console.print(f"Project-configured tools: {names or 'none'}")
            return

        raw = (
            input(
                f"  Remove tool '{tool_name}' from project '{project_name}'?"
                " This cannot be undone. [y/N]: "
            )
            .strip()
            .lower()
        )
        if raw not in ("y", "yes"):
            self.repl.console.print("Cancelled.")
            return

        del project_commands[tool_name]
        self._save_project_commands_json(project_name, project_commands)
        self.repl.console.print(f"[green]Tool removed:[/green] {tool_name}")
