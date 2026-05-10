"""Secrets-redaction helper and ASGI response middleware."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.security.redaction import (
    REDACTED,
    SENSITIVE_HEADER_RE,
    SENSITIVE_KEYS,
    URL_PARAM_BLACKLIST,
    redact_config,
    redact_query_string,
)

logger = logging.getLogger("tally.web.redact")

__all__ = [
    "REDACTED",
    "SENSITIVE_HEADER_RE",
    "SENSITIVE_KEYS",
    "URL_PARAM_BLACKLIST",
    "redact_config",
    "redact_query_string",
    "redact_exempt",
    "RedactionMiddleware",
    "install_redaction_middleware",
]


def redact_exempt[F: Callable[..., Any]](func: F) -> F:
    """Exempt a route from automatic redaction.

    Use only for routes whose response has been reviewed for secrets,
    or whose response must legitimately echo sensitive-pattern values
    (e.g., a field-spec catalog listing "password" as a form-field name).
    Document the exemption inline with a one-line comment.
    """
    setattr(func, "__redact_exempt__", True)
    return func


class RedactionMiddleware:
    """ASGI middleware: scrubs secrets from GET/HEAD JSON responses."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        if scope["method"] not in {"GET", "HEAD"}:
            await self._app(scope, receive, send)
            return

        response_start: Message | None = None
        body_parts: list[bytes] = []
        is_streaming = False
        is_passthrough = False

        async def _capture(message: Message) -> None:
            nonlocal response_start, is_streaming, is_passthrough

            if message["type"] == "http.response.start":
                response_start = message
                headers_map = dict(message.get("headers", []))
                ct = headers_map.get(b"content-type", b"").decode("latin-1")
                if ct.startswith("text/event-stream"):
                    is_passthrough = True
                    await send(message)
                return

            if message["type"] == "http.response.body":
                if is_passthrough:
                    await send(message)
                    return
                body_parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    is_streaming = True
                return

            await send(message)

        await self._app(scope, receive, _capture)

        if is_passthrough or response_start is None:
            return

        # Check for @redact_exempt on the matched route/endpoint.
        route = scope.get("route")
        endpoint = getattr(route, "endpoint", None) or scope.get("endpoint")
        if getattr(endpoint, "__redact_exempt__", False):
            await _flush(send, response_start, body_parts, is_streaming)
            return

        # Pass through chunked and non-JSON responses unchanged.
        headers_list: list[tuple[bytes, bytes]] = response_start.get("headers", [])
        headers_map = dict(headers_list)
        content_type = headers_map.get(b"content-type", b"").decode("latin-1")
        if is_streaming or not content_type.startswith("application/json"):
            await _flush(send, response_start, body_parts, is_streaming)
            return

        # Redact the JSON body.
        raw_body = b"".join(body_parts)
        try:
            obj = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            logger.warning("RedactionMiddleware: failed to parse JSON response body")
            await _flush(send, response_start, body_parts, False)
            return

        new_body = json.dumps(redact_config(obj)).encode()
        new_headers = [
            (name, value) for name, value in headers_list if name != b"content-length"
        ]
        new_headers.append((b"content-length", str(len(new_body)).encode()))
        await send({**response_start, "headers": new_headers})
        await send({"type": "http.response.body", "body": new_body, "more_body": False})


def install_redaction_middleware(app: FastAPI) -> None:
    app.add_middleware(RedactionMiddleware)


async def _flush(
    send: Send,
    response_start: Message,
    body_parts: list[bytes],
    is_streaming: bool,
) -> None:
    await send(response_start)
    if is_streaming:
        for i, part in enumerate(body_parts):
            await send(
                {
                    "type": "http.response.body",
                    "body": part,
                    "more_body": i < len(body_parts) - 1,
                }
            )
    else:
        await send(
            {
                "type": "http.response.body",
                "body": b"".join(body_parts),
                "more_body": False,
            }
        )
