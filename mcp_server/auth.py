"""Bearer token authentication for the MCP server."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

from starlette.responses import Response

from core.security.credentials import decrypt_value

if TYPE_CHECKING:
    from application.ports.mcp_token_repository import (
        McpTokenRepositoryPort,
    )

logger = logging.getLogger(__name__)


def validate_bearer_token(
    authorization: str,
    token_repo: McpTokenRepositoryPort,
    encryption_key: bytes,
) -> bool:
    """Validate an Authorization header against stored encrypted tokens."""
    if not authorization.startswith("Bearer "):
        return False
    incoming = authorization[7:]
    encrypted_tokens = token_repo.get_all_encrypted()
    for enc in encrypted_tokens:
        try:
            stored = decrypt_value(enc, encryption_key)
        except Exception:
            logger.warning("Skipping token that failed decryption")
            continue
        if secrets.compare_digest(stored, incoming):
            return True
    return False


class BearerTokenMiddleware:
    """ASGI middleware that validates Bearer tokens on every request."""

    def __init__(
        self,
        app: Any,
        token_repo: McpTokenRepositoryPort,
        encryption_key: bytes,
    ) -> None:
        self.app = app
        self.token_repo = token_repo
        self.encryption_key = encryption_key

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if not validate_bearer_token(auth, self.token_repo, self.encryption_key):
            response = Response(
                content="Unauthorized",
                status_code=401,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
