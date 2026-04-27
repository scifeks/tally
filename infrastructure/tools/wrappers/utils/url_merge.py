"""URL canonicalization helpers.

Phase 9 retired the ``URLMerger`` class — URL discovery now writes to
the ``url_findings`` table and the artifact builder rebuilds
``merged_urls.txt`` / ``merged_oas3.json`` from those rows JIT.
``_normalise_url`` is preserved here because the artifact builder
imports it for seed-line dedup canonicalization
(``application.url_inventory.artifact_builder.build_seeds``).
"""

from __future__ import annotations

from urllib.parse import urlsplit


def _normalise_url(url: str) -> str:
    """Return a canonical comparison key for *url*.

    Used only for deduplication — the original URL is preserved in output.

    Rules:
    - Lowercase the host.
    - Remove default ports (80 for http, 443 for https).
    - Strip trailing slashes from paths (except root ``/``).
    - Scheme differences (http vs https) are ignored — compare by
      ``host:port/path``.
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
