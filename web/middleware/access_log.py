"""Middleware: structured per-request access logging.

Emits one JSON line per HTTP request to the ``tally.web.access`` logger
(configured in ``web/server.py`` to write to ``logs/web-YYYY-MM-DD.log``).

Log fields: ``ts``, ``req_id``, ``method``, ``path`` (query with sensitive
params redacted), ``status``, ``latency_ms``, and ``error_class`` when
the inner app raised.

Never logs request/response bodies, cookies, Authorization header, or
X-CSRF-Token header.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from web.api._redact import redact_query_string

logger = logging.getLogger("tally.web.access")


class AccessLogMiddleware:
    """ASGI middleware: one JSON log line per HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        start = time.perf_counter()
        # Default to 500 so a crash before http.response.start still logs
        # something sensible.
        status_code = 500
        error_class: str | None = None

        async def _intercept(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, _intercept)
        except Exception as exc:
            error_class = type(exc).__name__
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            qs = scope.get("query_string", b"").decode("latin-1")
            redacted_qs = redact_query_string(qs)
            path = scope["path"]
            logged_path = f"{path}?{redacted_qs}" if redacted_qs else path

            record: dict[str, object] = {
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "req_id": request_id,
                "method": scope["method"],
                "path": logged_path,
                "status": status_code,
                "latency_ms": latency_ms,
            }
            if error_class is not None:
                record["error_class"] = error_class
            logger.info(json.dumps(record, separators=(",", ":")))
