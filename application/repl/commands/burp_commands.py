"""Burp integration commands for the REPL."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.locking.cancellation import CancellationToken
from application.mcp.ingest_service import McpIngestService
from application.tools.burp.note_enrichment import (
    NoteEnrichment,
)
from application.tools.burp.organizer_poller import (
    OrganizerPoller,
)
from core.project_paths import ProjectPaths
from factories.llm import create_llm_provider
from factories.persistence import create_finding_repo
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
            self._repl.console.print("[red]Usage:[/red] burp poll")
            return
        subcmd = args[0]
        if subcmd == "poll":
            self._cmd_poll()
        else:
            self._repl.console.print(f"[red]Unknown burp subcommand:[/red] {subcmd}")

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
