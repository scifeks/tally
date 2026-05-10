"""REPL adapter: no-op triage event sink.

The REPL output is driven by direct print() and logging. This sink
discards events to keep the REPL output byte-identical.
"""

from __future__ import annotations

from application.ports.triage_event_sink import NullTriageEventSink


class ConsoleTriageEventSink(NullTriageEventSink):
    """No-op sink for the REPL path."""
