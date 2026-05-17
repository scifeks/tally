"""Helpers for constructing NormalizedFinding objects in tests."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from domain.findings.normalization import (
    NormalizedFinding,
    normalise_finding_for_insert,
)


def _test_fingerprint(raw: dict[str, Any]) -> str:
    safe = {k: v for k, v in sorted(raw.items()) if isinstance(v, (str, int, float))}
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()


def normalize_test_findings(
    raw_findings: list[dict[str, Any]],
) -> list[NormalizedFinding]:
    """Normalize raw finding dicts for use with insert_findings."""
    result: list[NormalizedFinding] = []
    for raw in raw_findings:
        n = normalise_finding_for_insert(raw)
        fp = _test_fingerprint(raw)
        result.append(NormalizedFinding(n.columns, n.meta, fp))
    return result
