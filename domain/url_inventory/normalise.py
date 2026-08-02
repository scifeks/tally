"""URL canonicalization for seed-line deduplication."""

from __future__ import annotations

from urllib.parse import urlsplit


def normalise_url(url: str) -> str:
    """Return a canonical comparison key for *url*.

    Used only for deduplication; the original URL is preserved in output.
    """
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        scheme = parsed.scheme.lower()
        port = parsed.port
        if (
            port is None
            or (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            netloc = host
        else:
            netloc = f"{host}:{port}"
        path = parsed.path.rstrip("/") or "/"
        key = f"{netloc}{path}"
        if parsed.query:
            key = f"{key}?{parsed.query}"
        return key
    except Exception:
        return url.lower().rstrip("/")
