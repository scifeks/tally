"""Decode Burp REST API evidence segments from base64."""

from __future__ import annotations

import base64
from typing import Any

_SEGMENT_TYPES_WITH_DATA = frozenset({"DataSegment", "HighlightSegment"})


def decode_segment(segment: dict[str, Any]) -> str:
    """Decode a single evidence segment to a readable string."""
    seg_type = segment.get("type", "")
    if seg_type == "SnipSegment":
        length = segment.get("length", 0)
        return f"[...{length} bytes...]"
    if seg_type not in _SEGMENT_TYPES_WITH_DATA:
        return ""
    raw = segment.get("data", "")
    if not raw:
        return ""
    try:
        return base64.b64decode(raw).decode("utf-8", errors="replace")
    except Exception:
        return raw


def decode_evidence(evidence_list: list[dict[str, Any]]) -> str:
    """Decode all evidence entries into a single readable string."""
    if not evidence_list:
        return ""
    parts: list[str] = []
    for entry in evidence_list:
        rr = entry.get("request_response")
        if not rr:
            continue
        req_segments = rr.get("request", [])
        resp_segments = rr.get("response", [])
        req_text = "".join(decode_segment(s) for s in req_segments)
        resp_text = "".join(decode_segment(s) for s in resp_segments)
        if req_text:
            parts.append(f"Request:\n{req_text}")
        if resp_text:
            parts.append(f"Response:\n{resp_text}")
    return "\n\n".join(parts)
