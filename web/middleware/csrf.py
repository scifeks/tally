"""Middleware: CSRF double-submit cookie on state-mutating /api/* requests."""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT = frozenset({"/api/auth/exchange", "/api/auth/me"})

_ERR = json.dumps(
    {
        "error": {
            "code": "CSRF_VALIDATION_FAILED",
            "message": "CSRF token missing or invalid",
            "details": {},
        }
    }
)


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
            return Response(
                content=_ERR,
                status_code=403,
                media_type="application/json",
            )
        return await call_next(request)
