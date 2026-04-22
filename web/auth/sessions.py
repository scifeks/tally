"""Session store for cookie-based authentication."""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field


@dataclass
class SessionRecord:
    csrf_token: str
    created_at: float = field(default_factory=time.monotonic)


class SessionStore:
    """In-memory session store; resets on process death."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}

    def create(self) -> tuple[str, str]:
        """Mint a new session. Returns (session_id, csrf_token)."""
        session_id = secrets.token_hex(32)
        csrf_token = secrets.token_hex(32)
        self._sessions[session_id] = SessionRecord(csrf_token=csrf_token)
        return session_id, csrf_token

    def verify(self, session_id: str) -> bool:
        return session_id in self._sessions

    def get_csrf_token(self, session_id: str) -> str | None:
        record = self._sessions.get(session_id)
        return record.csrf_token if record else None

    def verify_csrf(self, session_id: str, token: str) -> bool:
        expected = self.get_csrf_token(session_id)
        if expected is None:
            return False
        return hmac.compare_digest(expected, token)

    def revoke(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
