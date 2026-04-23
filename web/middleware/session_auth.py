"""Middleware: session-cookie authentication on /api/* paths."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from web.api._errors import error_response

_EXEMPT = frozenset({"/api/auth/exchange", "/api/auth/me"})


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Require a valid tally_session cookie on /api/* paths (except exempt)."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in _EXEMPT:
            return await call_next(request)

        store = request.app.state.session_store
        session_id = request.cookies.get("tally_session", "")
        if not session_id or not store.verify(session_id):
            return error_response(401, "UNAUTHENTICATED", "Authentication required")
        request.state.session_id = session_id
        return await call_next(request)
