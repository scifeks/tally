"""Project management commands for the tally REPL."""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from core.repl.interface import REPL


class ProjectCommands:
    """Handlers for project management commands."""

    def __init__(self, repl: 'REPL') -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cmd_projects(self, _cmd: str, _args: List[str]) -> None:
        """List all projects in a Rich table."""
        projects = self.repl.projects.list_projects()
        active = self.repl.active_project

        if not projects:
            self.repl.console.print('[yellow]No projects found.[/yellow]')
            return

        table = Table(show_header=True, header_style='bold')
        table.add_column('Name', style='cyan', no_wrap=True)
        table.add_column('Created', style='white')
        table.add_column('Repositories', style='white', justify='right')
        table.add_column('Active', style='green', justify='center')

        for name in projects:
            info = self.repl.projects.get_project_info(name)
            created = ''
            repo_count = '0'
            if info:
                created = info.created[:10]
                repo_count = str(len(info.repositories))

            display_name = f'→ {name}' if name == active else name
            active_marker = '✓' if name == active else ''
            table.add_row(display_name, created, repo_count, active_marker)

        self.repl.console.print(table)

    def cmd_switch(self, _cmd: str, args: List[str]) -> None:
        """Switch active project."""
        if not args:
            self.repl.console.print('[red]Usage:[/red] switch <project-name>')
            return

        name = args[0]
        try:
            self.repl.projects.switch_project(name)
            self.repl.active_project = name
            self.repl.console.print(f'[green]✓ Switched to project: {name}[/green]')
        except ValueError:
            self.repl.console.print(f'[red]Project not found: {name}[/red]')

    def cmd_new_project(self, _cmd: str, _args: List[str]) -> None:
        """Create a new project interactively."""
        name = self.repl.projects.create_project()
        if name:
            self.repl.active_project = name

    def cmd_add_repo(self, _cmd: str, _args: List[str]) -> None:
        """Add a repository to the current project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' or 'switch <name>'[/yellow]"
            )
            return
        self.repl.projects.add_repository(self.repl.active_project)

    def cmd_repos(self, _cmd: str, _args: List[str]) -> None:
        """List configured repositories for the active project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' or 'switch <name>'[/yellow]"
            )
            return

        repos = self.repl.projects.config.load_repositories(self.repl.active_project)
        if not repos:
            self.repl.console.print('[yellow]No repositories configured.[/yellow]')
            return

        table = Table(show_header=True, header_style='bold')
        table.add_column('Name', style='cyan', no_wrap=True)
        table.add_column('Path', style='white')
        table.add_column('Languages', style='white')
        table.add_column('Base URLs', style='white')

        for repo in repos:
            langs = ', '.join(repo.languages) if repo.languages else '—'
            urls = ', '.join(repo.base_urls) if repo.base_urls else '—'
            table.add_row(repo.name, repo.path, langs, urls)

        self.repl.console.print(table)

    def cmd_edit_repo(self, _cmd: str, args: List[str]) -> None:
        """Edit an existing repository's config."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' or 'switch <name>'[/yellow]"
            )
            return
        if not args:
            self.repl.console.print('[red]Usage:[/red] edit-repo <repo-name>')
            return

        repo_name = args[0]
        try:
            self.repl.projects.edit_repository(self.repl.active_project, repo_name)
        except ValueError as exc:
            self.repl.console.print(f'[red]{exc}[/red]')

    def cmd_delete_repo(self, _cmd: str, args: List[str]) -> None:
        """Delete a repository's config from the active project."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' or 'switch <name>'[/yellow]"
            )
            return
        if not args:
            self.repl.console.print('[red]Usage:[/red] delete-repo <repo-name>')
            return

        repo_name = args[0]
        confirm = input(f"Delete repository '{repo_name}'? [y/N]: ").strip().lower()
        if confirm not in ('y', 'yes'):
            self.repl.console.print('[yellow]Cancelled.[/yellow]')
            return

        try:
            self.repl.projects.delete_repository(self.repl.active_project, repo_name)
            self.repl.console.print(f'[green]✓ Repository deleted: {repo_name}[/green]')
        except ValueError as exc:
            self.repl.console.print(f'[red]{exc}[/red]')

    def cmd_project_info(self, _cmd: str, _args: List[str]) -> None:
        """Show current project details."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'new-project' or 'switch <name>'[/yellow]"
            )
            return

        info = self.repl.projects.get_project_info(self.repl.active_project)
        if info is None:
            self.repl.console.print(
                f'[red]Could not load project: {self.repl.active_project}[/red]'
            )
            return

        created = info.created[:10] if len(info.created) >= 10 else info.created
        lines = [
            f'Created: {created}',
            f'Repositories: {len(info.repositories)}',
        ]
        if info.repositories:
            lines.append('')
            lines.append('Repositories:')
            for repo in info.repositories:
                lang_str = ', '.join(repo.languages) if repo.languages else 'none'
                lines.append(f'  \u2022 {repo.name} ({lang_str})')

        self.repl.console.print(
            Panel(
                '\n'.join(lines),
                title=f'Project: {self.repl.active_project}',
                expand=False,
            )
        )
