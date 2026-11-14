"""Persistence port for MCP bearer tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class McpTokenRow:
    """Read-only token metadata."""

    id: int
    name: str
    created_at: str


class McpTokenRepositoryPort(Protocol):
    """Port for storing and retrieving encrypted MCP tokens."""

    def create(self, name: str, encrypted_token: str) -> int:
        """Create a new token.

        Args:
            name: Unique token name.
            encrypted_token: Pre-encrypted token value.

        Returns:
            The new token ID.

        Raises:
            sqlite3.IntegrityError: If name already exists.
        """
        ...

    def list_all(self) -> list[McpTokenRow]:
        """List all token metadata (no encrypted values).

        Returns:
            Metadata rows sorted by created_at descending.
        """
        ...

    def revoke(self, name: str) -> bool:
        """Delete a token by name.

        Args:
            name: Token name to revoke.

        Returns:
            True if a token was deleted, False if not found.
        """
        ...

    def get_all_encrypted(self) -> list[str]:
        """Retrieve all encrypted token values.

        Used at startup to load tokens for decryption.

        Returns:
            List of encrypted token strings.
        """
        ...
