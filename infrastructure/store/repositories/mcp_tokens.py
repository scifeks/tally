"""SQLite repository for MCP bearer tokens in the registry database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from application.ports.mcp_token_repository import (
    McpTokenRepositoryPort,
    McpTokenRow,
)


class McpTokenRepository(McpTokenRepositoryPort):
    """Repository over the `mcp_tokens` table in tally.db."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create(self, name: str, encrypted_token: str) -> int:
        """Create a new token.

        Raises:
            sqlite3.IntegrityError: If name already exists.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO mcp_tokens (name, encrypted_token) VALUES (?, ?)",
                (name, encrypted_token),
            )
            return int(cur.lastrowid or 0)

    def list_all(self) -> list[McpTokenRow]:
        """List all token metadata, sorted by created_at descending."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM mcp_tokens ORDER BY created_at DESC"
            ).fetchall()
        return [
            McpTokenRow(
                id=int(row["id"]),
                name=str(row["name"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def revoke(self, name: str) -> bool:
        """Delete a token by name.

        Returns:
            True if a token was deleted, False if not found.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM mcp_tokens WHERE name = ?",
                (name,),
            )
            return cur.rowcount > 0

    def get_all_encrypted(self) -> list[str]:
        """Retrieve all encrypted token values."""
        with self._connect() as conn:
            rows = conn.execute("SELECT encrypted_token FROM mcp_tokens").fetchall()
        return [str(row["encrypted_token"]) for row in rows]
