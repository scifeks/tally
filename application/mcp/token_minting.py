"""Shared MCP bearer token minting for background scan and triage sessions."""

from __future__ import annotations

import secrets
from pathlib import Path

from infrastructure.store.repositories.mcp_tokens import McpTokenRepository


def mint_bearer_token(
    tag: str,
    *,
    base_path: Path,
) -> str:
    """Mint a short-lived MCP bearer token and persist its encrypted form.

    ``tag`` identifies the token in the ``mcp_tokens`` table (e.g.
    ``scan-background-42`` or ``triage-interactive-7``).
    """
    from core.security.credentials import (
        create_key_file,
        encrypt_value,
        get_encryption_key,
    )

    key_path = base_path / "mcp_credentials.key"
    if not key_path.exists():
        passphrase = secrets.token_urlsafe(32)
        key = create_key_file(passphrase, key_path)
    else:
        key = get_encryption_key(key_path)

    plaintext = secrets.token_urlsafe(32)
    encrypted = encrypt_value(plaintext, key)

    repo = McpTokenRepository(base_path / "tally.db")
    repo.revoke(tag)
    repo.create(tag, encrypted)

    return plaintext
