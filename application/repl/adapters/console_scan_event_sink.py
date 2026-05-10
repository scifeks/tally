"""REPL adapter: no-op scan event sink.

The REPL output is driven by direct OrchestratorDisplay calls. This sink
discards events to keep the REPL output byte-identical.
"""

from __future__ import annotations

from application.ports.scan_event_sink import NullScanEventSink


class ConsoleScanEventSink(NullScanEventSink):
    """No-op sink for the REPL path."""
