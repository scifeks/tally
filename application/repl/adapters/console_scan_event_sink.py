"""REPL adapter: receives scan events but does not render them.

The REPL has long-standing Rich console output driven by direct
``OrchestratorDisplay`` calls inside the scan_types modules. Phase 5.2
adds parallel event emission for the API surface; the REPL must remain
byte-identical, so this sink simply discards events.

If the REPL ever grows progress UI driven from semantic events
(rather than display calls), this is where it would live.
"""

from __future__ import annotations

from application.ports.scan_event_sink import NullScanEventSink


class ConsoleScanEventSink(NullScanEventSink):
    """No-op sink for the REPL path."""
