"""REPL adapter: receives triage events but does not render them.

The REPL has long-standing ``print()`` and logging output driven directly
by ``application/triage/runner.py``. Phase 6.2 adds parallel event
emission for the API surface; the REPL must remain byte-identical, so
this sink simply discards events.

If the REPL ever grows progress UI driven from semantic events
(rather than direct prints), this is where it would live.
"""

from __future__ import annotations

from application.ports.triage_event_sink import NullTriageEventSink


class ConsoleTriageEventSink(NullTriageEventSink):
    """No-op sink for the REPL path."""
