"""ReportRunRegistry — process-singleton tracking active report runs.

Mirrors :class:`application.tools.scan_run_registry.ScanRunRegistry`. The
cancel endpoint looks up cancellation tokens by ``report_id``. The
report worker thread unregisters itself in its ``finally`` block.

Report generation is single-active process-wide via ``LockRegistry``
slot ``"report"``, so this map will hold at most one entry at a time.
The registry still uses a dict keyed by ``report_id`` to mirror the
scan/triage registries and to keep the cancel API uniform.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class ReportRunHandle:
    report_id: int
    project_id: int
    cancel_token: CancellationToken


class ReportRunRegistry:
    """Process-singleton map of report_id -> ReportRunHandle."""

    def __init__(self) -> None:
        self._handles: dict[int, ReportRunHandle] = {}
        self._lock = threading.Lock()

    def register(
        self,
        *,
        report_id: int,
        project_id: int,
        cancel_token: CancellationToken,
    ) -> ReportRunHandle:
        handle = ReportRunHandle(
            report_id=report_id,
            project_id=project_id,
            cancel_token=cancel_token,
        )
        with self._lock:
            self._handles[report_id] = handle
        return handle

    def unregister(self, report_id: int) -> None:
        with self._lock:
            self._handles.pop(report_id, None)

    def get(self, report_id: int) -> ReportRunHandle | None:
        with self._lock:
            return self._handles.get(report_id)

    def list_for_project(self, project_id: int) -> list[ReportRunHandle]:
        with self._lock:
            return [h for h in self._handles.values() if h.project_id == project_id]

    def list_all(self) -> list[ReportRunHandle]:
        with self._lock:
            return list(self._handles.values())

    def reset(self) -> None:
        """Test helper — drop all entries."""
        with self._lock:
            self._handles.clear()


_REGISTRY: ReportRunRegistry | None = None


def get_report_run_registry() -> ReportRunRegistry:
    """Return the process-shared ReportRunRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ReportRunRegistry()
    return _REGISTRY
