"""Middleware: session-cookie authentication on /api/* paths."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from web.api._errors import error_response

_EXEMPT = frozenset(
    {
        "/api/v1/auth/exchange",
        "/api/v1/health",
    }
)


class SessionAuthMiddleware:
    """Require a valid tally_session cookie on /api/* paths (except exempt)."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        if not request.url.path.startswith("/api/"):
            await self._app(scope, receive, send)
            return
        if request.url.path in _EXEMPT:
            await self._app(scope, receive, send)
            return

        store = request.app.state.session_store
        session_id = request.cookies.get("tally_session", "")
        if not session_id or not store.verify(session_id):
            response = error_response(401, "UNAUTHENTICATED", "Authentication required")
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["session_id"] = session_id
        await self._app(scope, receive, send)
