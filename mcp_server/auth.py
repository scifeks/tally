"""Bearer token authentication for the MCP server."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from core.security.credentials import decrypt_value

if TYPE_CHECKING:
    from application.ports.mcp_token_repository import (
        McpTokenRepositoryPort,
    )


def validate_bearer_token(
    authorization: str,
    token_repo: McpTokenRepositoryPort,
    encryption_key: bytes,
) -> bool:
    """Validate an Authorization header against stored encrypted tokens.

    Args:
        authorization: The Authorization header value (e.g. "Bearer token123").
        token_repo: Repository for reading encrypted tokens.
        encryption_key: Fernet key for decrypting stored tokens.

    Returns:
        True if the bearer token matches a stored token, False otherwise.
    """
    if not authorization.startswith("Bearer "):
        return False
    incoming = authorization[7:]
    encrypted_tokens = token_repo.get_all_encrypted()
    for enc in encrypted_tokens:
        stored = decrypt_value(enc, encryption_key)
        if secrets.compare_digest(stored, incoming):
            return True
    return False
