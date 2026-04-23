"""Middleware: CSRF double-submit cookie on state-mutating /api/* requests."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from web.api._errors import error_response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT = frozenset({"/api/auth/exchange", "/api/auth/me"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Require X-CSRF-Token matching the session on mutating /api/* paths."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.method in _SAFE_METHODS:
            return await call_next(request)
        if request.url.path in _EXEMPT:
            return await call_next(request)

        session_id: str | None = getattr(request.state, "session_id", None)
        store = request.app.state.session_store
        csrf_header = request.headers.get("x-csrf-token", "")
        if not session_id or not store.verify_csrf(session_id, csrf_header):
            return error_response(
                403,
                "CSRF_VALIDATION_FAILED",
                "CSRF token missing or invalid",
            )
        return await call_next(request)
