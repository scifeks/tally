from __future__ import annotations

import json

from infrastructure.events.types import BusEvent
from infrastructure.security.redaction import redact_config


def format_sse_frame(event: BusEvent) -> str:
    """Render a BusEvent as a fully-formed SSE frame with redacted payload.

    Applies redact_config() to event.payload before serialising to ensure
    sensitive data is never sent over SSE.
    """
    safe_payload = redact_config(dict(event.payload))
    data = json.dumps(safe_payload)
    return f"event: {event.event_type}\ndata: {data}\n\n"
