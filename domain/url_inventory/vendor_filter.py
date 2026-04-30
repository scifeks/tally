"""Domain rule: which URL paths are vendor / dependency directories.

Pure rule with no I/O. Used at every URL-inventory ingest boundary
(``iter_oas3_rows``) so vendor paths never enter ``url_findings`` —
keeping the merged OAS3 artifact (which downstream DAST tools consume)
free of unreachable dependency URLs.

Path matching is segment-anchored: each indicator is wrapped with
leading and trailing slashes so ``/vendor/`` matches
``/api/vendor/foo`` but not ``/vendor-api/foo`` or ``/api/vendoring``.
"""

from __future__ import annotations

from collections.abc import Iterable

VENDOR_INDICATORS: frozenset[str] = frozenset(
    {
        "/vendor/",
        "/node_modules/",
        "/venv/",
        "/.venv/",
        "/site-packages/",
        "/__pycache__/",
        "/.git/",
        "/build/",
        "/dist/",
    }
)


def _normalize_indicator(name: str) -> str:
    return f"/{name.strip('/').lower()}/"


def is_vendor_path(path: str, *, extra_indicators: Iterable[str] = ()) -> bool:
    """Return True if *path* sits under a vendor / dependency directory.

    Args:
        path: A URL path (``/foo/bar``) or full URL — only the path
            portion is examined.
        extra_indicators: Additional directory names (with or without
            slashes) to treat as vendor dirs. Typically populated from
            ``Repository.ignore_dirs`` so user-configured exclusions
            apply to URL discovery.

    Matching is case-insensitive and segment-anchored.
    """
    if not path:
        return False
    haystack = path.lower()
    for indicator in VENDOR_INDICATORS:
        if indicator in haystack:
            return True
    for raw in extra_indicators:
        if not raw:
            continue
        if _normalize_indicator(raw) in haystack:
            return True
    return False
