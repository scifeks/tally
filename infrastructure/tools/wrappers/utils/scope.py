"""URL scope helpers for enforcing per-repo crawl boundaries.

Scope matching is deliberately protocol-agnostic: only the hostname and
port are compared, so ``http://`` vs ``https://`` differences never cause
a false-negative exclusion.  ``localhost`` and IP literals are treated as
valid FQDNs by ``urlsplit``, so no special-casing is required.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def scope_key(url: str) -> tuple[str, int] | None:
    """Return ``(hostname_lower, port)`` for *url*, or ``None`` if unparseable.

    Port defaults by scheme (http → 80, https → 443).  ``localhost`` and
    IPv4/IPv6 literals are returned as-is because ``urlsplit`` already
    exposes them via the ``hostname`` attribute.
    """
    try:
        # Bare hosts / paths (e.g. "localhost:8080") need a scheme so
        # urlsplit can parse them correctly.
        target = url if "://" in url else f"http://{url}"
        parsed = urlsplit(target)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if parsed.port:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80
    return host, port


def in_scope(url: str, base_url: str) -> bool:
    """Return ``True`` iff *url* and *base_url* share the same host:port.

    Protocol differences (http vs https) are ignored.  Returns ``False``
    when either URL cannot be parsed.
    """
    target = scope_key(url)
    allowed = scope_key(base_url)
    if target is None or allowed is None:
        return False
    return target == allowed
