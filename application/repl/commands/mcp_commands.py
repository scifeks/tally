"""REPL commands for MCP token management."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from rich.table import Table

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
        if not args or args[0] != "token":
            self._repl.console.print("Usage: mcp token <create|list|revoke>")
            return
        sub = args[1] if len(args) > 1 else ""
        if sub == "create":
            name = args[2] if len(args) > 2 else "default"
            self._create_token(name)
        elif sub == "list":
            self._list_tokens()
        elif sub == "revoke":
            if len(args) < 3:
                self._repl.console.print("Usage: mcp token revoke <name>")
                return
            self._revoke_token(args[2])
        else:
            self._repl.console.print("Usage: mcp token <create|list|revoke>")

    def _create_token(self, name: str) -> None:
        """Create a new MCP token with the given name."""
        try:
            db_path = self._repl.project_registry._repo.db_path
            repo = McpTokenRepository(db_path)

            # Generate plaintext token
            plaintext_token = secrets.token_urlsafe(32)

            # Get or create encryption key
            key_path = Path(self._repl.base_path) / "mcp_credentials.key"
            if not key_path.exists():
                passphrase = secrets.token_urlsafe(32)
                key = create_key_file(passphrase, key_path)
            else:
                key = get_encryption_key(key_path)

            # Encrypt and store
            encrypted_token = encrypt_value(plaintext_token, key)
            repo.create(name, encrypted_token)

            self._repl.console.print(f"[green]Token created:[/green] {name}")
            self._repl.console.print(
                f"[yellow]Token value (save this, it won't be shown "
                f"again):[/yellow]\n{plaintext_token}"
            )
        except ValueError as exc:
            self._repl.console.print(f"[red]Error:[/red] {exc}")
        except Exception as exc:
            self._repl.console.print(f"[red]Error creating token:[/red] {exc}")

    def _list_tokens(self) -> None:
        """List all MCP tokens."""
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
        """Revoke (delete) an MCP token by name."""
        try:
            db_path = self._repl.project_registry._repo.db_path
            repo = McpTokenRepository(db_path)
            if repo.revoke(name):
                self._repl.console.print(f"[green]Token revoked:[/green] {name}")
            else:
                self._repl.console.print(f"[yellow]Token not found:[/yellow] {name}")
        except Exception as exc:
            self._repl.console.print(f"[red]Error revoking token:[/red] {exc}")
