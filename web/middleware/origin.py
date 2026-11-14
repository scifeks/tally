"""Middleware: Origin/Referer check on state-mutating /api/* requests."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from web.api._errors import error_response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class OriginCheckMiddleware:
    """Reject cross-origin mutating requests to /api/* paths."""

    def __init__(
        self,
        app: ASGIApp,
        port: int,
        *,
        extra_origins: Iterable[str] = (),
    ) -> None:
        self._app = app
        self._allowed = {
            f"https://localhost:{port}",
            f"https://127.0.0.1:{port}",
            *extra_origins,
        }

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

        origin = request.headers.get("origin", "")
        if not origin:
            referer = request.headers.get("referer", "")
            if referer:
                parsed = urlparse(referer)
                origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._allowed:
            response = error_response(403, "FORBIDDEN", "Cross-origin request rejected")
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
