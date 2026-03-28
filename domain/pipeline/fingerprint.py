from __future__ import annotations

import hashlib
import json
from typing import Any

from infrastructure.tools.fingerprints import FINGERPRINT_REGISTRY


def _generic_fingerprint_key(finding: dict[str, Any]) -> str:
    safe = {
        k: v for k, v in sorted(finding.items()) if isinstance(v, (str, int, float))
    }
    return json.dumps(safe, sort_keys=True)


def compute_fingerprint(finding: dict[str, Any]) -> str:
    """Compute a stable sha256 fingerprint from per-tool key fields."""
    tool = finding.get("tool", "")
    key_fn = FINGERPRINT_REGISTRY.get(tool, _generic_fingerprint_key)
    key = key_fn(finding)
    return hashlib.sha256(key.encode()).hexdigest()
