"""Single-use handshake token registry."""

from __future__ import annotations

import time


class HandshakeRegistry:
    """In-memory single-use token store with TTL."""

    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._tokens: dict[str, float] = {}

    def register(self, token: str) -> None:
        self._tokens[token] = time.monotonic() + self._ttl

    def consume(self, token: str) -> bool:
        """Remove token and return True if it existed and has not expired."""
        expires_at = self._tokens.pop(token, None)
        if expires_at is None:
            return False
        return time.monotonic() <= expires_at
