"""Project management commands for the tally REPL."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from application.project.repositories_service import ProjectRepositoriesService
from application.tool_overrides.service import (
    ToolOverridesService,
    ToolOverrideValidationError,
)
from core.project_paths import ProjectPaths
from factories.persistence import create_overrides_repo
from infrastructure.tools.wrappers.utils.container_tool_probe import (
    probe_container_tools,
)

if TYPE_CHECKING:
    from application.repl.help_renderer import HelpRenderer
    from application.repl.interface import REPL
    from core.config.schemas import Repository


def _offer_garak_config(project_name: str, base_path: str, repo_id: int) -> None:
    paths = ProjectPaths.from_canonical(base_path, project_name)
    dest = paths.garak_config(repo_id)
    has_existing = dest.exists()
    if has_existing:
        hint = "  Garak config file (Enter to keep existing, or new path)"
    else:
        hint = "  Garak config file path (optional)"
    while True:
        raw = input(f"{hint}: ").strip()
        if not raw:
            return
        src = Path(raw).expanduser().resolve()
        if not src.exists():
            print(f"  File not found: {raw}")
            choice = input("  [r]etry / [s]kip? [r/s]: ").strip().lower()
            if choice not in ("r", "retry"):
                return
            continue
        if src.suffix not in (".yaml", ".yml"):
            print("  Garak config must be a YAML file (.yaml or .yml)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"  Garak config saved to {dest}")
        return


def _offer_docker_sca_overrides(
    project_name: str,
    base_path: str,
    repo: Repository,
) -> None:
    """Probe Docker containers for SCA tools and offer overrides."""
    if not repo.id or not repo.services:
        return
    service = repo.services[0]
    if not service.container_name or not service.docker_path:
        return

    detected = probe_container_tools(
        service.container_name,
        service.languages or [],
    )
    if not detected:
        print("  No SCA tools detected in container.")
        return

    paths = ProjectPaths.from_canonical(base_path, project_name)
    overrides_repo = create_overrides_repo(paths.findings_db)
    svc = ToolOverridesService(overrides_repo)

    created = 0
    for tool_name, tool_path in detected.items():
        answer = (
            input(
                f"  Use {tool_name} from container '{service.container_name}'? [y/N]: "
            )
            .strip()
            .lower()
        )
        if answer not in ("y", "yes"):
            continue
        try:
            svc.create(
                tool_name=tool_name,
                args_mode="stock",
                type="repo",
                location="docker",
                container_name=service.container_name,
                container_tool_path=tool_path,
                scope="service",
                repo_id=repo.id,
                service_name=service.name,
            )
            created += 1
            print(f"  Created {tool_name} override.")
        except (
            ToolOverrideValidationError,
            Exception,
        ) as exc:
            print(f"  Error creating {tool_name} override: {exc}")

    if created:
        print(
            f"  {created} SCA tool"
            f" {'override' if created == 1 else 'overrides'}"
            f" created for service '{service.name}'."
        )


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
        elif sub == "key":
            self.cmd_project_key(_cmd, args[1:])
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
            self._teardown_triage_containers()
            self.repl.console.print(f"[green]✓ Switched to project: {name}[/green]")
        except ValueError:
            self.repl.console.print(f"[red]Project not found: {name}[/red]")

    def _teardown_triage_containers(self) -> None:
        """Best-effort compose-down after a project switch."""
        try:
            from application.triage.container import (
                teardown_triage_containers,
            )

            teardown_triage_containers(Path(self.repl.base_path))
        except Exception:
            pass

    def cmd_new_project(self, _cmd: str, _args: list[str]) -> None:
        """Create a new project interactively."""
        name = self.repl.wizard.create_project()
        if name:
            self.repl.active_project = name
            for repo in self._active_repos(name):
                if repo.services and repo.services[0].container_name:
                    _offer_docker_sca_overrides(name, str(self.repl.base_path), repo)

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
        repo = self.repl.wizard.add_repository(self.repl.active_project)
        if repo is not None and repo.id is not None:
            _offer_garak_config(
                self.repl.active_project,
                str(self.repl.base_path),
                repo.id,
            )
            _offer_docker_sca_overrides(
                self.repl.active_project,
                str(self.repl.base_path),
                repo,
            )

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
            service = repo.services[0] if repo.services else None
            types = ", ".join(service.type) if service and service.type else "-"
            langs = (
                ", ".join(service.languages) if service and service.languages else "-"
            )
            urls = (
                ", ".join(service.base_urls) if service and service.base_urls else "-"
            )
            id_str = str(repo.id) if isinstance(repo.id, int) else "-"
            table.add_row(id_str, repo.name, types, repo.path, langs, urls)

        self.repl.console.print(table)

    def _resolve_repo_arg(self, arg: str) -> str | None:
        """Translate ``arg`` (id or name) into the canonical repo name."""
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
            updated = self.repl.wizard.edit_repository(
                self.repl.active_project, repo_name
            )
            if updated is not None and updated.id is not None:
                _offer_garak_config(
                    self.repl.active_project,
                    str(self.repl.base_path),
                    updated.id,
                )
                _offer_docker_sca_overrides(
                    self.repl.active_project,
                    str(self.repl.base_path),
                    updated,
                )
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
        paths = ProjectPaths.from_canonical(
            self.repl.projects.base_path,
            self.repl.active_project,
        )
        key_path = paths.credentials_key
        has_key = key_path.exists() or key_path.is_symlink()
        encryption_str = (
            "[green]active[/green]" if has_key else "[yellow]not configured[/yellow]"
        )
        lines = [
            f"Created: {created}",
            f"Repositories: {len(repos)}",
            f"Encryption: {encryption_str}",
        ]
        if repos:
            lines.append("")
            lines.append("Repositories:")
            for repo in repos:
                service = repo.services[0] if repo.services else None
                lang_str = (
                    ", ".join(service.languages)
                    if service and service.languages
                    else "none"
                )
                lines.append(f"  • {repo.name} ({lang_str})")

        self.repl.console.print(
            Panel(
                "\n".join(lines),
                title=f"Project: {self.repl.active_project}",
                expand=False,
            )
        )

    def cmd_project_key(self, _cmd: str, args: list[str]) -> None:
        """project key [status|setup|change]: encryption key management."""
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project switch <name>' first.[/yellow]"
            )
            return
        if not args:
            self.repl.console.print(
                "Usage: project key <subcommand>\n\n"
                "  status  Show encryption status and key file location\n"
                "  setup   Create an encryption key for this project\n"
                "  change  Rotate passphrase or move key file"
            )
            return
        sub = args[0].lower()
        if sub == "status":
            self._key_status()
        elif sub == "setup":
            self._key_setup()
        elif sub == "change":
            self._key_change()
        else:
            self.repl.console.print(
                f"[red]Unknown subcommand:[/red] project key {sub}\n"
                "Usage: project key [status|setup|change]"
            )

    def _key_status(self) -> None:
        """Show encryption status for the current project."""
        assert self.repl.active_project is not None
        paths = ProjectPaths.from_canonical(
            self.repl.projects.base_path,
            self.repl.active_project,
        )
        key_path = paths.credentials_key
        if not key_path.exists() and not key_path.is_symlink():
            self.repl.console.print(
                "[yellow]Encryption is not configured for this "
                "project.[/yellow]\n"
                "Run 'project key setup' to create a key."
            )
            return
        actual = key_path.resolve()
        is_symlink = key_path.is_symlink()
        lines = ["[green]Encryption is active.[/green]"]
        if is_symlink:
            lines.append(f"Key file: {actual}")
            lines.append(f"Symlink: {key_path}")
        else:
            lines.append(f"Key file: {key_path}")
        self.repl.console.print("\n".join(lines))

    def _key_setup(self) -> None:
        """Create an encryption key for a project that lacks one."""
        assert self.repl.active_project is not None
        paths = ProjectPaths.from_canonical(
            self.repl.projects.base_path,
            self.repl.active_project,
        )
        key_path = paths.credentials_key
        if key_path.exists() or key_path.is_symlink():
            self.repl.console.print(
                "[yellow]Encryption is already configured.[/yellow]\n"
                "Use 'project key change' to rotate the key."
            )
            return

        from application.credentials.service import CredentialsService
        from application.project.wizard import (
            collect_key_path,
            collect_passphrase,
        )
        from factories.persistence import create_repo_repo

        passphrase = collect_passphrase()
        key_dest = collect_key_path(key_path)
        self.repl.projects.setup_credentials_key(passphrase, key_dest, key_path)

        service = CredentialsService(create_repo_repo(paths.findings_db))
        service.reencrypt_repos()

        self.repl.console.print(
            "[green]Encryption key created.[/green]\n"
            "Existing auth credentials have been encrypted."
        )

    def _key_change(self) -> None:
        """Change passphrase and optionally move the key file."""
        assert self.repl.active_project is not None
        paths = ProjectPaths.from_canonical(
            self.repl.projects.base_path,
            self.repl.active_project,
        )
        key_path = paths.credentials_key
        if not key_path.exists() and not key_path.is_symlink():
            self.repl.console.print(
                "[yellow]No encryption key found.[/yellow]\n"
                "Use 'project key setup' to create one."
            )
            return

        from application.credentials.service import CredentialsService
        from application.project.wizard import (
            collect_key_path,
            collect_passphrase,
        )
        from factories.persistence import create_repo_repo

        passphrase = collect_passphrase()
        old_actual = key_path.resolve()
        print(f"\n  Current key file: {old_actual}")
        move = input("  Move key file? [y/N]: ").strip().lower()
        if move in ("y", "yes"):
            final_dest = collect_key_path(key_path)
        else:
            final_dest = old_actual

        service = CredentialsService(create_repo_repo(paths.findings_db))
        try:
            service.change_key(paths, passphrase, final_dest)
        except Exception:
            self.repl.console.print(
                "[red]Re-encryption failed. Old key and data preserved.[/red]"
            )
            raise

        self.repl.console.print(
            "[green]Key changed successfully.[/green]\n"
            "All auth credentials re-encrypted."
        )
