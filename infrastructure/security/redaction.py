from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

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


def redact_query_string(query: str) -> str:
    """Redact sensitive params from a raw URL query string.

    Preserves order, encoding, and blank values. Single source of truth
    for query-string scrubbing; reused by `_redact_url` and by the
    access-log middleware.
    """
    if not query:
        return ""
    parts = []
    for name, value in parse_qsl(query, keep_blank_values=True):
        enc_name = quote(name, safe="")
        if any(s in name.lower() for s in URL_PARAM_BLACKLIST):
            parts.append(f"{enc_name}={REDACTED}")
        else:
            parts.append(f"{enc_name}={quote(value, safe='')}")
    return "&".join(parts)


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    return urlunsplit(parts._replace(query=redact_query_string(parts.query)))
