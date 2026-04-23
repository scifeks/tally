"""Middleware: Host header allowlist (DNS rebinding protection)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from web.api._errors import error_response


class HostHeaderMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Host is not localhost or 127.0.0.1 on our port."""

    def __init__(self, app: ASGIApp, port: int) -> None:
        super().__init__(app)
        self._allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.headers.get("host", "") not in self._allowed:
            return error_response(400, "INVALID_HOST", "Invalid Host header")
        return await call_next(request)
