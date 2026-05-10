"""Track active scan runs via a process-singleton registry.

Maps ``run_id`` to ``ScanRunHandle`` while a scan is in flight, allowing
cancel endpoints to find the ``CancellationToken`` and signal a stop. The
service that started the scan unregisters in its ``finally`` block.

Thread-safe via an internal mutex; reads and writes are O(1).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from application.locking.cancellation import CancellationToken


@dataclass
class ScanRunHandle:
    run_id: int
    project_id: int
    cancel_token: CancellationToken
    # Most recent tool_started seen on the bus, used to seed mid-scan
    # SSE subscribers so they see the active tool/repo without waiting
    # for the next event. Updated by EventBusScanSink.emit().
    current_repo: str | None = None
    current_tool: str | None = None


class ScanRunRegistry:
    """Process-singleton map of run_id -> ScanRunHandle for active scans."""

    def __init__(self) -> None:
        self._handles: dict[int, ScanRunHandle] = {}
        self._lock = threading.Lock()

    def register(
        self,
        *,
        run_id: int,
        project_id: int,
        cancel_token: CancellationToken,
    ) -> ScanRunHandle:
        handle = ScanRunHandle(
            run_id=run_id,
            project_id=project_id,
            cancel_token=cancel_token,
        )
        with self._lock:
            self._handles[run_id] = handle
        return handle

    def unregister(self, run_id: int) -> None:
        with self._lock:
            self._handles.pop(run_id, None)

    def get(self, run_id: int) -> ScanRunHandle | None:
        with self._lock:
            return self._handles.get(run_id)

    def set_current(self, run_id: int, *, repo: str, tool: str) -> None:
        """Record the latest tool_started for an active run.

        No-op if the run is not registered (e.g. the event arrives
        after unregister has already cleaned up).
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.current_repo = repo
                handle.current_tool = tool

    def list_for_project(self, project_id: int) -> list[ScanRunHandle]:
        with self._lock:
            return [h for h in self._handles.values() if h.project_id == project_id]

    def list_all(self) -> list[ScanRunHandle]:
        with self._lock:
            return list(self._handles.values())

    def reset(self) -> None:
        """Test helper to drop all entries."""
        with self._lock:
            self._handles.clear()


_REGISTRY: ScanRunRegistry | None = None


def get_scan_run_registry() -> ScanRunRegistry:
    """Return the process-shared ScanRunRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ScanRunRegistry()
    return _REGISTRY
