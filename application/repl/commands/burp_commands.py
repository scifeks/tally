"""Burp integration commands for the REPL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.locking import JobBusy
from application.locking.cancellation import CancellationToken
from application.mcp.ingest_service import McpIngestService
from application.project.repositories_service import (
    ProjectRepositoriesService,
)
from application.tools.burp.note_enrichment import (
    NoteEnrichment,
)
from application.tools.burp.organizer_poller import (
    OrganizerPoller,
)
from application.tools.orchestrator import ScanCancelled
from core.project_paths import ProjectPaths
from factories.llm import create_llm_provider
from factories.persistence import (
    create_finding_repo,
    create_repo_repo,
    create_scan_repos,
    create_url_finding_repo,
)
from factories.scanning import get_scan_service
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.organizer_state import (
    OrganizerStateRepository,
)
from infrastructure.store.repositories.runs import (
    RunRepository,
)
from infrastructure.tools.burp.mcp_client import BurpMcpClient

if TYPE_CHECKING:
    from application.repl.interface import REPL

logger = logging.getLogger(__name__)


class BurpCommands:
    def __init__(self, repl: REPL) -> None:
        self._repl = repl

    def cmd_burp(self, _cmd: str, args: list) -> None:
        if not args:
            self._show_help()
            return
        sub = args[0].lower()
        if sub == "poll":
            self._cmd_poll()
        elif sub == "scan":
            self._cmd_scan(args[1:])
        else:
            self._repl.console.print(f"[red]Unknown subcommand:[/red] {sub}")
            self._show_help()

    def _cmd_poll(self) -> None:
        if self._repl.active_project is None:
            self._repl.console.print(
                "[red]No active project.[/red] Run 'project switch <name>' first."
            )
            return

        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None:
            self._repl.console.print("[red]Active project not found.[/red]")
            return

        burp_cfg = self._repl.config.global_config.burp
        if not burp_cfg or not burp_cfg.mcp_url:
            self._repl.console.print(
                "[red]Burp MCP URL not configured."
                "[/red] Set burp.mcp_url in "
                "config/global.json."
            )
            return

        paths = ProjectPaths.from_registry_row(row)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = create_finding_repo(paths.findings_db)
        state_repo = OrganizerStateRepository(factory)
        fetcher = BurpMcpClient(burp_cfg.mcp_url)
        ingest = McpIngestService(
            finding_repo=finding_repo,
            run_repo=run_repo,
        )

        enrichment: NoteEnrichment | None = None
        try:
            provider = create_llm_provider("enrichment", self._repl.base_path)
            enrichment = NoteEnrichment(provider)
        except Exception:
            pass

        poller = OrganizerPoller(
            fetcher=fetcher,
            state_repo=state_repo,
            ingest_service=ingest,
            project_id=row.id,
            poll_interval=float(burp_cfg.poll_interval_seconds),
            note_enrichment=enrichment,
        )

        interval = burp_cfg.poll_interval_seconds
        self._repl.console.print(
            f"Polling Burp Organizer every {interval}s... (Ctrl+C to stop)"
        )
        cancel_token = CancellationToken()
        try:
            poller.run(cancel_token)
        except KeyboardInterrupt:
            cancel_token.set()
            self._repl.console.print("\nBurp poll stopped.")

    def _cmd_scan(self, args: list[str]) -> None:
        if not self._repl.active_project:
            self._repl.console.print(
                "[yellow]No active project. Use 'project add' first.[/yellow]"
            )
            return

        config_name = " ".join(args) if args else None

        urls = self._collect_base_urls()
        if not urls:
            self._repl.console.print(
                "[red]No base URLs configured in"
                " project repositories.[/red]\n"
                "Add base URLs to a repository"
                " service with 'repo edit'."
            )
            return

        from core.config.manager import ConfigManager

        cfg = ConfigManager(str(self._repl.base_path))
        if cfg.global_config.burp is None:
            self._repl.console.print(
                "[red]Burp is not configured.[/red]\n"
                "Add a burp section to"
                " config/global.json with base_url."
            )
            return

        project_id = self._resolve_project_id()
        paths = ProjectPaths.from_canonical(
            self._repl.base_path,
            self._repl.active_project,
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
        self._repl.console.print(f"[bold]Starting {label}...[/bold]")

        try:
            handle = get_scan_service().start_scan(
                project_id=project_id,
                project_name=self._repl.active_project,
                base_path=str(self._repl.base_path),
                tool_registry=self._repl.tool_registry,
                run_repo=run_repo,
                chat_session_repo=chat_repo,
                profiles_repo=profiles_repo,
                finding_repo=finding_repo,
                repo_repo=repo_repo,
                url_finding_repo=url_finding_repo,
                prompt=RichConsolePromptAdapter(),
                reporter=StdoutProgressReporter(),
                display=OrchestratorDisplay(self._repl.console),
                burp_urls=urls,
                burp_config_name=config_name,
            )
        except JobBusy as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
            return

        try:
            handle.result.result()
        except ScanCancelled:
            self._repl.console.print("[yellow]Burp scan cancelled.[/yellow]")
        except Exception as exc:
            self._repl.console.print(f"[red]Burp scan failed:[/red] {exc}")

    def _collect_base_urls(self) -> list[str]:
        assert self._repl.active_project is not None
        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None:
            return []
        svc = ProjectRepositoriesService(
            self._repl.project_registry,
            self._repl.config,
        )
        urls: list[str] = []
        for repo in svc.list_active(row.id):
            for s in repo.services:
                urls.extend(s.base_urls)
        return urls

    def _resolve_project_id(self) -> int:
        assert self._repl.active_project is not None
        row = self._repl.project_registry.resolve_by_name(self._repl.active_project)
        if row is None:
            raise ValueError(f"project not found: {self._repl.active_project}")
        return row.id

    def _show_help(self) -> None:
        self._repl.console.print(
            "Usage: burp <subcommand>\n"
            "  poll              "
            "Poll Organizer for new items\n"
            "  scan [config]     "
            "Start a Burp crawl-and-audit scan"
        )
