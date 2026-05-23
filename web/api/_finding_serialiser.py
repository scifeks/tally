"""Normalize Finding rows into the shape the API and SSE surfaces expect."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from domain.findings.entry import Finding
from domain.findings.normalization import ANALYST_META_KEYS

# Matches type_secret, type_vulnerability, type_weakness, etc.
_TYPE_FLAG_RE = re.compile(r"^type_[a-z]+$")


def serialise_finding(
    finding: Finding, lock_state: tuple[bool, str | None]
) -> dict[str, Any]:
    """Normalize a Finding into the dict shape the API returns."""
    payload: dict[str, Any] = asdict(finding)
    meta = payload.get("meta", {})
    for key in ANALYST_META_KEYS:
        if key in meta:
            payload.setdefault(key, meta.pop(key))
    payload["meta"] = {k: v for k, v in meta.items() if not _TYPE_FLAG_RE.match(k)}
    payload["id_fingerprint"] = payload.pop("fingerprint")
    payload["enriched"] = 1 if payload["enriched"] else 0
    payload["should_report"] = 1 if payload["should_report"] else 0

    payload["target"] = payload.get("url") or ""

    is_locked, lock_holder = lock_state
    payload["is_locked"] = is_locked
    payload["lock_holder"] = lock_holder
    return payload
