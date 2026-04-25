"""ScanRunRegistry — process-singleton tracking active scan runs.

Phase 5.6 needs a way for the cancel endpoints to find the
``CancellationToken`` for a running scan. The registry maps
``run_id`` -> live entry while the background scan thread holds the
``LockRegistry`` slot. Cancel endpoints look up tokens here. The scan
thread unregisters itself in its ``finally`` block.

Thread-safe via an internal mutex; reads and writes are O(1).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class ScanRunHandle:
    run_id: int
    project_id: int
    cancel_token: CancellationToken


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

    def list_for_project(self, project_id: int) -> list[ScanRunHandle]:
        with self._lock:
            return [h for h in self._handles.values() if h.project_id == project_id]

    def list_all(self) -> list[ScanRunHandle]:
        with self._lock:
            return list(self._handles.values())

    def reset(self) -> None:
        """Test helper — drop all entries."""
        with self._lock:
            self._handles.clear()


_REGISTRY: ScanRunRegistry | None = None


def get_scan_run_registry() -> ScanRunRegistry:
    """Return the process-shared ScanRunRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ScanRunRegistry()
    return _REGISTRY
