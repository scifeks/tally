from __future__ import annotations

import hashlib
import json
from typing import Any

from application.rag.ingestor import ToolHandlerFactory


def _generic_fingerprint_key(finding: dict[str, Any]) -> str:
    safe = {
        k: v for k, v in sorted(finding.items()) if isinstance(v, (str, int, float))
    }
    return json.dumps(safe, sort_keys=True)


def compute_fingerprint(finding: dict[str, Any]) -> str:
    """Compute a stable sha256 fingerprint from per-tool key fields.

    Delegates to the tool's ToolHandler.fingerprint_key() when available;
    falls back to a generic hash over all scalar finding fields.
    """
    tool = finding.get("tool", "")
    handler = ToolHandlerFactory.load(tool) if tool else None
    if handler is not None:
        key = handler.fingerprint_key(finding)
    else:
        key = _generic_fingerprint_key(finding)
    return hashlib.sha256(key.encode()).hexdigest()
