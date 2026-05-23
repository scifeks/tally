"""Helpers for manual finding creation."""

from __future__ import annotations

import hashlib

from domain.tools.scan_types.models import SEGMENT_ORDER

_SEGMENT_TO_DOMAIN: dict[str, str] = {
    "sast": "code",
    "sca": "code",
    "secrets": "code",
    "web": "web",
    "llm": "code",
}


def derive_domain(segment: str) -> str:
    """Return the domain for a given segment."""
    if segment not in _SEGMENT_TO_DOMAIN:
        raise ValueError(f"Unknown segment {segment!r}. Valid: {SEGMENT_ORDER}")
    return _SEGMENT_TO_DOMAIN[segment]


def manual_fingerprint(title: str, segment: str, location: str) -> str:
    """Generate a SHA-256 fingerprint for a manual finding."""
    raw = f"{title}:{segment}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()
