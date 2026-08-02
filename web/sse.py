"""SSE frame formatting for web event streams."""

from __future__ import annotations

import json

from core.security.redaction import redact_config
from domain.pipeline.bus_event import BusEvent


def format_sse_frame(event: BusEvent) -> str:
    """Render a BusEvent as an SSE frame with redacted payload."""
    safe_payload = redact_config(dict(event.payload))
    data = json.dumps(safe_payload)
    return f"event: {event.event_type}\ndata: {data}\n\n"
