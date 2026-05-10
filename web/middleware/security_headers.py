"""Middleware: emit security response headers (CSP, XFO, nosniff, Referrer-Policy)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach Tally's hardening headers to every response.

    The Content-Security-Policy intentionally omits ``'unsafe-inline'`` from
    both ``script-src`` and ``style-src``. Tailwind v4 + Vite production
    builds emit static CSS / bundled JS, and React's ``style={{...}}`` prop
    sets DOM properties at runtime (which CSP does not block), so strict
    ``'self'`` is sufficient for the production SPA bundle.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
