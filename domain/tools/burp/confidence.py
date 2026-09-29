"""Burp confidence mapping and fingerprint parsing."""

from __future__ import annotations

from urllib.parse import unquote

from domain.tools.constants import CONFIDENCE_CONFIRMED

_CONFIDENCE_MAP: dict[str, str] = {
    "certain": CONFIDENCE_CONFIRMED,
    "firm": "probable",
    "tentative": "potential",
}


def map_burp_confidence(burp_confidence: str) -> str:
    """Map Burp's confidence level to Tally's confidence constants."""
    return _CONFIDENCE_MAP.get(burp_confidence.lower(), "potential")


def determine_finding_status() -> str:
    """All Burp findings are confirmed: the scanner exploited the
    vulnerability to discover it.
    """
    return CONFIDENCE_CONFIRMED


def parse_fingerprint(fingerprint: str) -> dict[str, str]:
    """Parse a Burp fingerprint string into key-value pairs.

    Fingerprints use colon-separated key=value pairs with
    URL-encoded values. Leading colon is stripped.
    """
    if not fingerprint:
        return {}
    result: dict[str, str] = {}
    stripped = fingerprint.lstrip(":")
    for part in stripped.split(":"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key] = unquote(value)
    return result
