"""Secrets-redaction helper and ASGI response middleware."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("tally.web.redact")

REDACTED = "***REDACTED***"
SENSITIVE_KEYS = frozenset({"api_key", "password", "token", "secret", "authorization"})
SENSITIVE_HEADER_RE = re.compile(r"^(authorization|cookie|x-api-key)$", re.IGNORECASE)
URL_PARAM_BLACKLIST = ("token", "secret", "password", "auth")


def redact_config(payload: Any) -> Any:
    """Return a new object with secrets replaced by REDACTED.

    Never mutates the input.
    """
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "auth":
                continue
            if key.lower() in SENSITIVE_KEYS:
                out[key] = REDACTED
            elif (key == "headers" or key.lower().endswith("_headers")) and isinstance(
                value, dict
            ):
                out[key] = {
                    h: (REDACTED if SENSITIVE_HEADER_RE.match(h) else v)
                    for h, v in value.items()
                }
            else:
                out[key] = redact_config(value)
        return out
    if isinstance(payload, list):
        return [redact_config(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_config(item) for item in payload)
    if isinstance(payload, str) and payload.startswith(("http://", "https://")):
        return _redact_url(payload)
    return payload


def redact_exempt[F: Callable[..., Any]](func: F) -> F:
    """Mark a GET/HEAD route handler as exempt from automatic redaction.

    Apply only to routes whose response has been reviewed and is known
    safe, OR whose response must echo a value that superficially matches
    a sensitive-field pattern for legitimate reasons (e.g. a field-spec
    catalog that lists "password" as a form-field name).
    Every use must carry a one-line comment explaining why.
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


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    params = parse_qsl(parts.query, keep_blank_values=True)
    redacted = [
        (
            name,
            REDACTED if any(s in name.lower() for s in URL_PARAM_BLACKLIST) else value,
        )
        for name, value in params
    ]
    return urlunsplit(parts._replace(query=urlencode(redacted)))
