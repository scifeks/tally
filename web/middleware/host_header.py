"""Middleware: Host header allowlist (DNS rebinding protection)."""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_ERR = json.dumps(
    {
        "error": {
            "code": "BAD_REQUEST",
            "message": "Invalid Host header",
            "details": {},
        }
    }
)


class HostHeaderMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Host is not localhost or 127.0.0.1 on our port."""

    def __init__(self, app: ASGIApp, port: int) -> None:
        super().__init__(app)
        self._allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.headers.get("host", "") not in self._allowed:
            return Response(
                content=_ERR,
                status_code=400,
                media_type="application/json",
            )
        return await call_next(request)
