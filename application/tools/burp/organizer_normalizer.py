"""Normalize raw Organizer HTTP strings into structured fields."""

from __future__ import annotations

from dataclasses import dataclass

_NO_RESPONSE = "<no response>"


@dataclass(frozen=True)
class NormalizedHttp:
    """Structured fields parsed from an Organizer item's HTTP evidence.

    ``status_code`` is ``None`` when the item had no response or the
    response line could not be parsed. ``host`` is ``None`` when the
    request carried no Host header.
    """

    method: str
    url: str
    host: str | None
    status_code: int | None


def normalize_http(request: str, response: str) -> NormalizedHttp:
    """Parse method, request target, host, and status from raw HTTP."""
    method, url = _parse_request_line(request)
    host = _parse_host(request)
    status_code = _parse_status_code(response)
    return NormalizedHttp(
        method=method,
        url=url,
        host=host,
        status_code=status_code,
    )


def _parse_request_line(request: str) -> tuple[str, str]:
    first_line = request.split("\n", 1)[0].strip()
    parts = first_line.split()
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[1]


def _parse_host(request: str) -> str | None:
    for line in request.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("host:"):
            return stripped[len("host:") :].strip() or None
    return None


def _parse_status_code(response: str) -> int | None:
    if not response or response.strip() == _NO_RESPONSE:
        return None
    parts = response.split("\n", 1)[0].split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None
