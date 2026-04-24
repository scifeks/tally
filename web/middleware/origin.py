"""Middleware: Origin/Referer check on state-mutating /api/* requests."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from web.api._errors import error_response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin mutating requests to /api/* paths."""

    def __init__(
        self,
        app: ASGIApp,
        port: int,
        *,
        extra_origins: Iterable[str] = (),
    ) -> None:
        super().__init__(app)
        self._allowed = {
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
            *extra_origins,
        }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        origin = request.headers.get("origin", "")
        if not origin:
            referer = request.headers.get("referer", "")
            if referer:
                parsed = urlparse(referer)
                origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._allowed:
            return error_response(403, "FORBIDDEN", "Cross-origin request rejected")
        return await call_next(request)
