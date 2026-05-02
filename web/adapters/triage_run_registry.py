"""Process-singleton tracking the active triage run.

Maps ``scan_run_id`` to live entries while the background triage thread
holds the ``LockRegistry`` slot. The cancel endpoint looks up tokens here.
The triage thread unregisters itself in its ``finally`` block. Triage is
single-active process-wide via ``LockRegistry``, so this map holds at most
one entry. Thread-safe via an internal mutex.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class TriageRunHandle:
    scan_run_id: int
    project_id: int
    cancel_token: CancellationToken


class TriageRunRegistry:
    """Process-singleton map of scan_run_id -> TriageRunHandle."""

    def __init__(self) -> None:
        self._handles: dict[int, TriageRunHandle] = {}
        self._lock = threading.Lock()

    def register(
        self,
        *,
        scan_run_id: int,
        project_id: int,
        cancel_token: CancellationToken,
    ) -> TriageRunHandle:
        handle = TriageRunHandle(
            scan_run_id=scan_run_id,
            project_id=project_id,
            cancel_token=cancel_token,
        )
        with self._lock:
            self._handles[scan_run_id] = handle
        return handle

    def unregister(self, scan_run_id: int) -> None:
        with self._lock:
            self._handles.pop(scan_run_id, None)

    def get(self, scan_run_id: int) -> TriageRunHandle | None:
        with self._lock:
            return self._handles.get(scan_run_id)

    def list_for_project(self, project_id: int) -> list[TriageRunHandle]:
        with self._lock:
            return [h for h in self._handles.values() if h.project_id == project_id]

    def list_all(self) -> list[TriageRunHandle]:
        with self._lock:
            return list(self._handles.values())

    def reset(self) -> None:
        """Test helper to drop all entries."""
        with self._lock:
            self._handles.clear()


_REGISTRY: TriageRunRegistry | None = None


def get_triage_run_registry() -> TriageRunRegistry:
    """Return the process-shared TriageRunRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = TriageRunRegistry()
    return _REGISTRY
