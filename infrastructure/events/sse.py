from __future__ import annotations

import json

from infrastructure.events.types import BusEvent
from infrastructure.security.redaction import redact_config


def format_sse_frame(event: BusEvent) -> str:
    """Render a BusEvent as a fully-formed SSE frame string.

    Applies redact_config() to event.payload unconditionally before
    serialising. Callers in Phases 5.5 / 6.5 / 7.6 / 8.9 MUST use this
    helper — it is the single chokepoint for SSE-bound event bytes and
    the only way redaction can be enforced by construction.
    """
    safe_payload = redact_config(dict(event.payload))
    data = json.dumps(safe_payload)
    return f"event: {event.event_type}\ndata: {data}\n\n"
