"""Serialisation of ``Finding`` rows for the findings HTTP surface.

Shared between ``web/api/findings.py`` (response bodies) and
``web/adapters/event_bus_finding_sink.py`` (SSE payload).
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from domain.findings.entry import Finding

# Matches type_secret, type_vulnerability, type_weakness, etc.
_TYPE_FLAG_RE = re.compile(r"^type_[a-z]+$")


def serialise_finding(
    finding: Finding, lock_state: tuple[bool, str | None]
) -> dict[str, Any]:
    """Serialise a Finding for the API response.

    The named ``fingerprint`` column is exposed as ``id_fingerprint`` so
    it cannot collide with semgrep's scanner fingerprint stored in
    ``meta``. ``type_*`` flags written by the ChromaDB ingestor are
    stripped from ``meta`` before the response leaves the adapter.
    """
    result: dict[str, Any] = asdict(finding)
    result["meta"] = {
        k: v for k, v in result["meta"].items() if not _TYPE_FLAG_RE.match(k)
    }
    result["id_fingerprint"] = result.pop("fingerprint")
    result["enriched"] = 1 if result["enriched"] else 0
    result["should_report"] = 1 if result["should_report"] else 0

    is_locked, lock_holder = lock_state
    result["is_locked"] = is_locked
    result["lock_holder"] = lock_holder
    return result
