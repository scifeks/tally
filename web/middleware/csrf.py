"""Middleware: CSRF double-submit cookie on state-mutating /api/* requests."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from web.api._errors import error_response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT = frozenset({"/api/v1/auth/exchange"})


class CSRFMiddleware:
    """Require X-CSRF-Token matching the session on mutating /api/* paths."""

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
        if request.method in _SAFE_METHODS:
            await self._app(scope, receive, send)
            return
        if request.url.path in _EXEMPT:
            await self._app(scope, receive, send)
            return

        session_id: str | None = scope.get("state", {}).get("session_id")
        store = request.app.state.session_store
        csrf_header = request.headers.get("x-csrf-token", "")
        if not session_id or not store.verify_csrf(session_id, csrf_header):
            response = error_response(
                403,
                "CSRF_VALIDATION_FAILED",
                "CSRF token missing or invalid",
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
