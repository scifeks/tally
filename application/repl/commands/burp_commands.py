"""Burp Suite commands for the Tally REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.locking import JobBusy
from application.project.repositories_service import (
    ProjectRepositoriesService,
)
from application.tools.orchestrator import ScanCancelled
from core.project_paths import ProjectPaths
from factories.persistence import (
    create_finding_repo,
    create_repo_repo,
    create_scan_repos,
    create_url_finding_repo,
)
from factories.scanning import get_scan_service

if TYPE_CHECKING:
    from application.repl.interface import REPL


class BurpCommands:
    """Handlers for Burp Suite REPL commands."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    def cmd_burp(self, _cmd: str, args: list[str]) -> None:
        """burp <subcommand>"""
        if not args:
            self._show_help()
            return
        sub = args[0].lower()
        if sub == "scan":
            self._cmd_scan(args[1:])
        else:
            self.repl.console.print(f"[red]Unknown subcommand:[/red] {sub}")
            self._show_help()

    def _cmd_scan(self, args: list[str]) -> None:
        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        config_name = " ".join(args) if args else None

        urls = self._collect_base_urls()
        if not urls:
            self.repl.console.print(
                "[red]No base URLs configured in"
                " project repositories.[/red]\n"
                "Add base URLs to a repository"
                " service with 'repo edit'."
            )
            return

        from core.config.manager import ConfigManager

        cfg = ConfigManager(str(self.repl.base_path))
        if cfg.global_config.burp is None:
            self.repl.console.print(
                "[red]Burp is not configured.[/red]\n"
                "Add a burp section to"
                " config/global.json with base_url."
            )
            return

        project_id = self._resolve_project_id()
        paths = ProjectPaths.from_canonical(
            self.repl.base_path,
            self.repl.active_project,
        )
        run_repo, chat_repo, profiles_repo, _ = create_scan_repos(paths.findings_db)
        finding_repo = create_finding_repo(paths.findings_db)
        repo_repo = create_repo_repo(paths.findings_db)
        url_finding_repo = create_url_finding_repo(paths.findings_db)

        from application.repl.adapters.orchestrator_display import (
            OrchestratorDisplay,
        )
        from application.repl.adapters.rich_console_prompt import (
            RichConsolePromptAdapter,
        )
        from application.repl.adapters.stdout_progress_reporter import (
            StdoutProgressReporter,
        )

        label = "burp scan"
        if config_name:
            label = f"burp scan ({config_name})"
        self.repl.console.print(f"[bold]Starting {label}...[/bold]")

        try:
            handle = get_scan_service().start_scan(
                project_id=project_id,
                project_name=self.repl.active_project,
                base_path=str(self.repl.base_path),
                tool_registry=self.repl.tool_registry,
                run_repo=run_repo,
                chat_session_repo=chat_repo,
                profiles_repo=profiles_repo,
                finding_repo=finding_repo,
                repo_repo=repo_repo,
                url_finding_repo=url_finding_repo,
                prompt=RichConsolePromptAdapter(),
                reporter=StdoutProgressReporter(),
                display=OrchestratorDisplay(self.repl.console),
                burp_urls=urls,
                burp_config_name=config_name,
            )
        except JobBusy as exc:
            self.repl.console.print(f"[red]Error:[/red] {exc}")
            return

        try:
            handle.result.result()
        except ScanCancelled:
            self.repl.console.print("[yellow]Burp scan cancelled.[/yellow]")
        except Exception as exc:
            self.repl.console.print(f"[red]Burp scan failed:[/red] {exc}")

    def _collect_base_urls(self) -> list[str]:
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            return []
        svc = ProjectRepositoriesService(
            self.repl.project_registry,
            self.repl.config,
        )
        urls: list[str] = []
        for repo in svc.list_active(row.id):
            for s in repo.services:
                urls.extend(s.base_urls)
        return urls

    def _resolve_project_id(self) -> int:
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            raise ValueError(f"project not found: {self.repl.active_project}")
        return row.id

    def _show_help(self) -> None:
        self.repl.console.print(
            "Usage: burp <subcommand>\n"
            "  scan [config_name]"
            "  Start a Burp crawl-and-audit scan"
        )
