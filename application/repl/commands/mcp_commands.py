"""REPL commands for MCP server and token management."""

from __future__ import annotations

import logging
import secrets
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from rich.table import Table

from application.mcp.config_file import write_mcp_json
from core.config.manager import ConfigManager
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

logger = logging.getLogger(__name__)


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
        elif verb == "server":
            self._dispatch_server(args[1:])
        elif verb == "serve":
            self._start_serve()
        else:
            self._print_usage()

    def _print_usage(self) -> None:
        self._repl.console.print(
            "Usage: mcp <token|server|serve>\n"
            "  mcp token create [name]  "
            "Create a bearer token\n"
            "  mcp token list           "
            "List tokens\n"
            "  mcp token revoke <name>  "
            "Revoke a token\n"
            "  mcp server create        "
            "Write .mcp.json from config\n"
            "  mcp serve                "
            "Start the MCP server"
        )

    # -- server sub-commands --

    def _dispatch_server(self, args: list[str]) -> None:
        sub = args[0] if args else ""
        if sub == "create":
            self._create_server_config()
        else:
            self._repl.console.print("Usage: mcp server create")

    def _create_server_config(self) -> None:
        try:
            config = ConfigManager(self._repl.base_path)
            mcp_cfg = config.global_config.mcp
            base = Path(self._repl.base_path)
            path = write_mcp_json(base, mcp_cfg.host, mcp_cfg.port)
            if (path).stat().st_size > 0:
                self._repl.console.print(f"[green].mcp.json written to {path}[/green]")
        except Exception as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")

    # -- serve --

    def _start_serve(self) -> None:
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

            mcp_json = base / ".mcp.json"
            if not mcp_json.exists():
                write_mcp_json(base, mcp_cfg.host, mcp_cfg.port)
                repl.console.print(f"[green]Created .mcp.json at {mcp_json}[/green]")

            from mcp_server.server import start_mcp_server

            port = mcp_cfg.port

            def _worker() -> None:
                try:
                    start_mcp_server(
                        port,
                        repl.project_registry,
                        repl.tool_registry,
                        token_repo,
                        encryption_key,
                        base,
                    )
                except Exception:
                    logger.exception("MCP server crashed")

            thread = threading.Thread(
                target=_worker,
                name="mcp-server",
                daemon=True,
            )
            thread.start()
            repl.console.print(
                f"[green]MCP server started on"
                f" {mcp_cfg.host}:{port}[/green]\n"
                "The server runs in the background. "
                "It will stop when you exit the REPL."
            )
        except Exception as exc:
            self._repl.console.print(f"[red]Error starting MCP server:[/red] {exc}")

    # -- token sub-commands --

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
