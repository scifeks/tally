"""REPL commands for MCP server and token management."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.table import Table

from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from core.security.credentials import (
    create_key_file,
    encrypt_value,
    get_encryption_key,
)
from infrastructure.store.repositories.mcp_tokens import (
    McpTokenRepository,
)

if TYPE_CHECKING:
    from application.repl.interface import REPL


class McpCommands:
    def __init__(self, repl: REPL) -> None:
        self._repl = repl

    def cmd_mcp(self, _cmd: str, args: list[str]) -> None:
        if not args:
            self._print_usage()
            return

        verb = args[0]
        if verb == "token":
            self._dispatch_token(args[1:])
        elif verb == "show-config":
            self._show_config()
        elif verb == "serve":
            self._dispatch_serve(args[1:])
        elif verb == "triage":
            self._dispatch_triage(args[1:])
        else:
            self._print_usage()

    def _print_usage(self) -> None:
        self._repl.console.print(
            "Usage: mcp <token|show-config|serve|triage>\n"
            "  mcp token create [name]  "
            "Create a bearer token\n"
            "  mcp token list           "
            "List tokens\n"
            "  mcp token revoke <name>  "
            "Revoke a token\n"
            "  mcp show-config          "
            "Show Claude Code config snippet\n"
            "  mcp serve                "
            "Manage the MCP server (start|stop|restart|status)\n"
            "  mcp triage prepare       "
            "Create triage batches for MCP processing"
        )

    # Show config

    def _show_config(self) -> None:
        from application.mcp.config_file import (
            format_show_config,
        )
        from core.security.credentials import decrypt_value

        try:
            repl = self._repl
            config = ConfigManager(repl.base_path)
            mcp_cfg = config.global_config.mcp
            base = Path(repl.base_path)

            key_path = base / "mcp_credentials.key"
            if not key_path.exists():
                repl.console.print(
                    "[red]No MCP tokens found.[/red] "
                    "Run 'mcp token create <name>' first."
                )
                return
            key = get_encryption_key(key_path)

            db_path = repl.project_registry._repo.db_path
            repo = McpTokenRepository(db_path)
            encrypted = repo.get_all_encrypted()
            if not encrypted:
                repl.console.print(
                    "[red]No MCP tokens found.[/red] "
                    "Run 'mcp token create <name>' first."
                )
                return

            token = decrypt_value(encrypted[0], key)
            result = format_show_config(mcp_cfg.host, mcp_cfg.port, token)
            c = repl.console
            c.print("[bold]Run this command in your terminal:[/bold]\n")
            c.print(f"  {result.cli_command}")
            c.print("\n[dim]One-time setup. Restart Claude Code after running.[/dim]")
        except Exception as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")

    # Serve

    def _dispatch_serve(self, args: list[str]) -> None:
        if not args:
            self._serve_submenu()
            return
        action = args[0]
        if action == "start":
            self._serve_start()
        elif action == "stop":
            self._serve_stop()
        elif action == "restart":
            self._serve_restart()
        elif action == "status":
            self._serve_status()
        else:
            self._serve_submenu()

    def _serve_submenu(self) -> None:
        self._repl.console.print("[bold]MCP serve commands:[/bold]")
        self._repl.console.print("  mcp serve start    Start the MCP server")
        self._repl.console.print("  mcp serve stop     Stop the MCP server")
        self._repl.console.print("  mcp serve restart  Restart the MCP server")
        self._repl.console.print("  mcp serve status   Show server status")

    def _serve_start(self) -> None:
        from application.mcp.lifecycle import start_mcp_server_managed

        try:
            repl = self._repl
            config = ConfigManager(repl.base_path)
            mcp_cfg = config.global_config.mcp
            base = Path(repl.base_path)

            projects = repl.project_registry.list_active()
            if not projects:
                repl.console.print(
                    "[red]No projects configured.[/red] Create a project first."
                )
                return

            key_path = base / "mcp_credentials.key"
            if not key_path.exists():
                repl.console.print(
                    "[red]No MCP tokens found.[/red] "
                    "Run 'mcp token create <name>' first."
                )
                return
            encryption_key = get_encryption_key(key_path)

            db_path = repl.project_registry._repo.db_path
            token_repo = McpTokenRepository(db_path)
            tokens = token_repo.list_all()
            if not tokens:
                repl.console.print(
                    "[red]No MCP tokens found.[/red] "
                    "Run 'mcp token create <name>' first."
                )
                return

            handle = start_mcp_server_managed(
                port=mcp_cfg.port,
                host=mcp_cfg.host,
                project_registry=repl.project_registry,
                tool_registry=repl.tool_registry,
                token_repo=token_repo,
                encryption_key=encryption_key,
                base_path=str(base),
                source="repl",
            )
            repl.console.print(
                f"[green]MCP server started on {handle.host}:{handle.port}[/green]"
            )
        except RuntimeError as exc:
            self._repl.console.print(f"[red]{exc}[/red]")

    def _serve_stop(self) -> None:
        from application.mcp.lifecycle import stop_mcp_server

        if stop_mcp_server():
            self._repl.console.print("[green]MCP server stopped[/green]")
        else:
            self._repl.console.print("[yellow]No active MCP server[/yellow]")

    def _serve_restart(self) -> None:
        self._serve_stop()
        import time

        time.sleep(0.5)
        self._serve_start()

    def _serve_status(self) -> None:
        from application.mcp.registry import get_mcp_server_registry

        handle = get_mcp_server_registry().get()
        if handle is None:
            self._repl.console.print("[dim]MCP server: not running[/dim]")
        else:
            self._repl.console.print(
                f"[green]MCP server: running on"
                f" {handle.host}:{handle.port}"
                f" (source: {handle.source})[/green]"
            )

    # Triage

    def _dispatch_triage(self, args: list[str]) -> None:
        if not args or args[0] != "prepare":
            self._repl.console.print(
                f"[yellow]Usage: mcp triage prepare {escape('[run_id]')}[/yellow]"
            )
            return
        run_id = int(args[1]) if len(args) > 1 else None
        self._triage_prepare(run_id)

    def _triage_prepare(self, run_id: int | None) -> None:
        from application.triage.batch_creator import (
            create_triage_batches,
        )
        from infrastructure.store.connection import (
            ConnectionFactory,
        )
        from infrastructure.store.repositories.runs import (
            RunRepository,
        )
        from infrastructure.store.repositories.triage import (
            TriageBatchRepository,
        )

        repl = self._repl
        if repl.active_project is None:
            repl.console.print(
                "[red]No active project.[/red] Run 'project switch <name>' first."
            )
            return
        row = repl.project_registry.resolve_by_name(repl.active_project)
        if row is None or row.archived_at:
            repl.console.print("[red]Active project not found.[/red]")
            return

        paths = ProjectPaths.from_registry_row(row)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        run_repo = RunRepository(factory)

        if run_id is None:
            run_id = run_repo.latest_run_id()
        if run_id is None:
            repl.console.print("[red]No scan runs found[/red]")
            return

        triage_repo = TriageBatchRepository(factory)
        batches = create_triage_batches(
            run_id=run_id,
            triage_repo=triage_repo,
            tool_registry=repl.tool_registry,
            max_findings_per_batch=4,
        )
        total = sum(count for _, count in batches)
        repl.console.print(
            f"[green]Created {len(batches)} batches"
            f" ({total} findings) for run {run_id}[/green]"
        )

    # Token subcommands

    def _dispatch_token(self, args: list[str]) -> None:
        sub = args[0] if args else ""
        if sub == "create":
            name = args[1] if len(args) > 1 else "default"
            self._create_token(name)
        elif sub == "list":
            self._list_tokens()
        elif sub == "revoke":
            if len(args) < 2:
                self._repl.console.print("Usage: mcp token revoke <name>")
                return
            self._revoke_token(args[1])
        else:
            self._repl.console.print("Usage: mcp token <create|list|revoke>")

    def _create_token(self, name: str) -> None:
        try:
            db_path = self._repl.project_registry._repo.db_path
            repo = McpTokenRepository(db_path)

            plaintext_token = secrets.token_urlsafe(32)

            key_path = Path(self._repl.base_path) / "mcp_credentials.key"
            if not key_path.exists():
                passphrase = secrets.token_urlsafe(32)
                key = create_key_file(passphrase, key_path)
            else:
                key = get_encryption_key(key_path)

            encrypted_token = encrypt_value(plaintext_token, key)
            repo.create(name, encrypted_token)

            self._repl.console.print(f"[green]Token created:[/green] {name}")
            self._repl.console.print(
                "[yellow]Token value (save this, it won't"
                " be shown again):[/yellow]"
                f"\n{plaintext_token}"
            )
        except ValueError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
        except Exception as exc:
            self._repl.console.print(f"[red]Error creating token:[/red] {exc}")

    def _list_tokens(self) -> None:
        try:
            db_path = self._repl.project_registry._repo.db_path
            repo = McpTokenRepository(db_path)
            tokens = repo.list_all()

            if not tokens:
                self._repl.console.print("[yellow]No MCP tokens found.[/yellow]")
                return

            table = Table(
                show_header=True,
                header_style="bold",
                padding=(0, 1),
            )
            table.add_column("Name", style="cyan")
            table.add_column("Created At", style="white")

            for token in tokens:
                table.add_row(token.name, token.created_at)

            self._repl.console.print(table)
        except Exception as exc:
            self._repl.console.print(f"[red]Error listing tokens:[/red] {exc}")

    def _revoke_token(self, name: str) -> None:
        try:
            db_path = self._repl.project_registry._repo.db_path
            repo = McpTokenRepository(db_path)
            if repo.revoke(name):
                self._repl.console.print(f"[green]Token revoked:[/green] {name}")
            else:
                self._repl.console.print(f"[yellow]Token not found:[/yellow] {name}")
        except Exception as exc:
            self._repl.console.print(f"[red]Error revoking token:[/red] {exc}")
