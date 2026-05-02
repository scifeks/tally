"""Domain rule: which URL paths are vendor or dependency directories.

Pure rule with no I/O. Prevents vendor paths from entering the URL
inventory so the merged OAS3 artifact is free of unreachable
dependency URLs. Path matching is segment-anchored: ``/vendor/``
matches ``/api/vendor/foo`` but not ``/vendor-api/foo`` or
``/api/vendoring``.
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
    """Return True if *path* sits under a vendor or dependency directory.

    Args:
        path: A URL path (``/foo/bar``) or full URL; only the path
            portion is examined.
        extra_indicators: Additional directory names (with or without
            slashes) to treat as vendor dirs, typically from
            ``Repository.ignore_dirs``.

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
