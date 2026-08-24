from __future__ import annotations

import json

from core.security.redaction import redact_config
from domain.pipeline.bus_event import BusEvent


def format_sse_frame(event: BusEvent) -> str:
    """Render a BusEvent as a fully-formed SSE frame with redacted payload.

    Applies redact_config() to event.payload before serializing to ensure
    sensitive data is never sent over SSE.
    """
    safe_payload = redact_config(dict(event.payload))
    data = json.dumps(safe_payload)
    return f"event: {event.event_type}\ndata: {data}\n\n"
