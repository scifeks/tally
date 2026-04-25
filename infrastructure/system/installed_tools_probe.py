"""Probe-once installed-tools adapter for ``InstalledToolsPort``.

Walks the tool registry exactly once per process and freezes the result.
Subsequent calls return the cached snapshot. Designed to be invoked at
REPL boot (or web-server startup), so the snapshot is established before
any adapter consults it.
"""

from __future__ import annotations

import logging
import threading

from application.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class InstalledToolsProbe:
    """Probe ``tool.check_available()`` once and cache the result."""

    def __init__(self) -> None:
        self._snapshot: frozenset[str] | None = None
        self._lock = threading.Lock()

    def installed(self) -> frozenset[str]:
        if self._snapshot is None:
            with self._lock:
                if self._snapshot is None:
                    self._snapshot = self._probe()
        return self._snapshot

    @staticmethod
    def _probe() -> frozenset[str]:
        installed: set[str] = set()
        for tool in tool_registry.get_all_tools():
            try:
                if tool.check_available():
                    installed.add(tool.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "installed-tools probe: %s.check_available() raised: %s",
                    tool.name,
                    exc,
                )
        return frozenset(installed)
