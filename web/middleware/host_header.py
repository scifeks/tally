"""Middleware: Host header allowlist (DNS rebinding protection)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from web.api._errors import error_response


class HostHeaderMiddleware:
    """Reject requests whose Host is not in the allowlist for our port."""

    def __init__(self, app: ASGIApp, port: int, *, host: str = "127.0.0.1") -> None:
        self._app = app
        self._allowed = {
            f"localhost:{port}",
            f"127.0.0.1:{port}",
            f"{host}:{port}",
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        if request.headers.get("host", "") not in self._allowed:
            response = error_response(400, "INVALID_HOST", "Invalid Host header")
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
