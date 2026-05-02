"""Project management commands for the tally REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from application.project.repositories_service import ProjectRepositoriesService

if TYPE_CHECKING:
    from application.repl.help_renderer import HelpRenderer
    from application.repl.interface import REPL
    from core.config.schemas import Repository


class ProjectCommands:
    """Handlers for project management commands."""

    def __init__(self, repl: REPL, help_renderer: HelpRenderer) -> None:
        self.repl = repl
        self.help_renderer = help_renderer

    def _active_repos(self, project_name: str) -> list[Repository]:
        """Return active repos for *project_name*, or ``[]`` if unknown."""
        row = self.repl.project_registry.resolve_by_name(project_name)
        if row is None:
            return []
        service = ProjectRepositoriesService(
            self.repl.project_registry, self.repl.projects.config
        )
        return service.list_active(row.id)

    # Grouped command entrypoints (scoped help or subcommand dispatch)

    def cmd_project(self, _cmd: str, args: list[str]) -> None:
        """project [add|switch|list|info]: project management."""
        if not args:
            self.help_renderer.render("project")
            return
        sub = args[0].lower()
        if sub == "add":
            self.cmd_new_project(_cmd, args[1:])
        elif sub == "switch":
            self.cmd_switch(_cmd, args[1:])
        elif sub == "list":
            self.cmd_projects(_cmd, args[1:])
        elif sub == "info":
            self.cmd_project_info(_cmd, args[1:])
        elif sub == "delete":
            self.cmd_delete_project(_cmd, args[1:])
        elif sub == "edit":
            self.cmd_edit_project(_cmd, args[1:])
        else:
            self.repl.console.print(
                f"[red]Unknown subcommand:[/red] project {sub}\n"
                "Type [bold]project[/bold] for available subcommands"
            )

    def cmd_repo(self, _cmd: str, args: list[str]) -> None:
        """repo [add|delete|edit|list]: repository management."""
        if not args:
            self.help_renderer.render("repo")
            return
        sub = args[0].lower()
        if sub == "add":
            self.cmd_add_repo(_cmd, args[1:])
        elif sub == "delete":
            self.cmd_delete_repo(_cmd, args[1:])
        elif sub == "edit":
            self.cmd_edit_repo(_cmd, args[1:])
        elif sub == "list":
            self.cmd_repos(_cmd, args[1:])
        else:
            self.repl.console.print(
                f"[red]Unknown subcommand:[/red] repo {sub}\n"
                "Type [bold]repo[/bold] for available subcommands"
            )

    # Commands

    def cmd_projects(self, _cmd: str, _args: list[str]) -> None:
        """List all projects in a Rich table."""
        rows = self.repl.project_registry.list_active()
        active = self.repl.active_project

        if not rows:
            self.repl.console.print("[yellow]No projects found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("Id", style="white", justify="right")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Created", style="white")
        table.add_column("Repositories", style="white", justify="right")
        table.add_column("Active", style="green", justify="center")

        for row in rows:
            name = row.name
            info = self.repl.projects.get_project_info(name)
            created = ""
            repo_count = "0"
            if info:
                created = info.created[:10]
                repo_count = str(len(self._active_repos(name)))

            display_name = f"→ {name}" if name == active else name
            active_marker = "✓" if name == active else ""
            table.add_row(str(row.id), display_name, created, repo_count, active_marker)

        self.repl.console.print(table)

    def cmd_switch(self, _cmd: str, args: list[str]) -> None:
        """Switch active project."""
        if not args:
            self.repl.console.print("[red]Usage:[/red] project switch <name>")
            return

        name = args[0]
        try:
            self.repl.projects.switch_project(name)
            self.repl.active_project = name
            self.repl.console.print(f"[green]✓ Switched to project: {name}[/green]")
        except ValueError:
            self.repl.console.print(f"[red]Project not found: {name}[/red]")

    def cmd_new_project(self, _cmd: str, _args: list[str]) -> None:
        """Create a new project interactively."""
        name = self.repl.wizard.create_project()
        if name:
            self.repl.active_project = name

    def cmd_delete_project(self, _cmd: str, args: list[str]) -> None:
        """project delete <name>: delete a project and all its data."""
        if not args:
            self.repl.console.print("[yellow]Usage:[/yellow] project delete <name>")
            return

        project_name = args[0]

        confirm = (
            input(f"Delete project '{project_name}' and ALL its data? [y/N]: ")
            .strip()
            .lower()
        )
        if confirm not in ("y", "yes"):
            self.repl.console.print("[yellow]Cancelled.[/yellow]")
            return

        try:
            self.repl.projects.delete_project(project_name)
        except ValueError as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        self.repl.console.print(f"[green]Project '{project_name}' deleted.[/green]")

        # Clear active project in the running REPL session
        if self.repl.active_project == project_name:
            self.repl.active_project = None
            self.repl.console.print(
                "[yellow]Active project cleared. Use 'project add' or "
                "'project switch' to set a new one.[/yellow]"
            )

    def cmd_edit_project(self, _cmd: str, args: list[str]) -> None:
        """project edit [<name>]: edit project-level settings interactively.

        If <name> is omitted and there is an active project, edits that project.
        """
        if args:
            project_name = args[0]
        elif self.repl.active_project:
            project_name = self.repl.active_project
        else:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project edit <name>' or switch to a project first.[/yellow]"
            )
            return
        try:
            self.repl.wizard.edit_project(project_name)
        except ValueError as exc:
            self.repl.console.print(f"[red]{exc}[/red]")

    def cmd_add_repo(self, _cmd: str, _args: list[str]) -> None:
        """Add a repository to the current project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>'[/yellow]"
            )
            return
        self.repl.wizard.add_repository(self.repl.active_project)

    def cmd_repos(self, _cmd: str, _args: list[str]) -> None:
        """List configured repositories for the active project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>'[/yellow]"
            )
            return

        repos = self._active_repos(self.repl.active_project)
        if not repos:
            self.repl.console.print("[yellow]No repositories configured.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="white", no_wrap=True)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Type", style="white")
        table.add_column("Path", style="white")
        table.add_column("Languages", style="white")
        table.add_column("Base URLs", style="white", overflow="fold")

        for repo in repos:
            types = ", ".join(repo.type) if repo.type else "-"
            langs = ", ".join(repo.languages) if repo.languages else "-"
            urls = ", ".join(repo.base_urls) if repo.base_urls else "-"
            id_str = str(repo.id) if isinstance(repo.id, int) else "-"
            table.add_row(id_str, repo.name, types, repo.path, langs, urls)

        self.repl.console.print(table)

    def _resolve_repo_arg(self, arg: str) -> str | None:
        """Translate ``arg`` (id or name) into the canonical repo name.

        ``repo edit`` and ``repo delete`` accept either the integer DB id
        (e.g. ``repo edit 3``) or the repo name. This helper centralizes
        resolution so the wizard and project-manager callees keep their
        name-based contract intact.

        Returns the repo name on success or ``None`` when the argument
        doesn't match any active repository.
        """
        if not self.repl.active_project:
            return None
        repos = self._active_repos(self.repl.active_project)
        if arg.isdigit():
            target_id = int(arg)
            for r in repos:
                if isinstance(r.id, int) and r.id == target_id:
                    return r.name
            return None
        for r in repos:
            if r.name == arg:
                return r.name
        return None

    def cmd_edit_repo(self, _cmd: str, args: list[str]) -> None:
        """Edit an existing repository's config."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>'[/yellow]"
            )
            return
        if not args:
            self.repl.console.print("[red]Usage:[/red] repo edit <id-or-name>")
            return

        repo_name = self._resolve_repo_arg(args[0])
        if repo_name is None:
            self.repl.console.print(
                f"[red]Unknown repository (id or name): {args[0]}[/red]"
            )
            return
        try:
            self.repl.wizard.edit_repository(self.repl.active_project, repo_name)
        except ValueError as exc:
            self.repl.console.print(f"[red]{exc}[/red]")

    def cmd_delete_repo(self, _cmd: str, args: list[str]) -> None:
        """Delete a repository's config from the active project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>'[/yellow]"
            )
            return
        if not args:
            self.repl.console.print("[red]Usage:[/red] repo delete <id-or-name>")
            return

        repo_name = self._resolve_repo_arg(args[0])
        if repo_name is None:
            self.repl.console.print(
                f"[red]Unknown repository (id or name): {args[0]}[/red]"
            )
            return
        confirm = input(f"Delete repository '{repo_name}'? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            self.repl.console.print("[yellow]Cancelled.[/yellow]")
            return

        try:
            self.repl.projects.delete_repository(self.repl.active_project, repo_name)
            self.repl.console.print(f"[green]✓ Repository deleted: {repo_name}[/green]")
        except ValueError as exc:
            self.repl.console.print(f"[red]{exc}[/red]")

    def cmd_project_info(self, _cmd: str, _args: list[str]) -> None:
        """Show current project details."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>'[/yellow]"
            )
            return

        info = self.repl.projects.get_project_info(self.repl.active_project)
        if info is None:
            self.repl.console.print(
                f"[red]Could not load project: {self.repl.active_project}[/red]"
            )
            return

        created = info.created[:10] if len(info.created) >= 10 else info.created
        repos = self._active_repos(self.repl.active_project)
        lines = [
            f"Created: {created}",
            f"Repositories: {len(repos)}",
        ]
        if repos:
            lines.append("")
            lines.append("Repositories:")
            for repo in repos:
                lang_str = ", ".join(repo.languages) if repo.languages else "none"
                lines.append(f"  \u2022 {repo.name} ({lang_str})")

        self.repl.console.print(
            Panel(
                "\n".join(lines),
                title=f"Project: {self.repl.active_project}",
                expand=False,
            )
        )
