"""Process-singleton tracking active draft generation runs."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class DraftRunHandle:
    section: str
    project_id: int
    cancel_token: CancellationToken


class DraftRunRegistry:
    """Process-singleton map of section -> DraftRunHandle."""

    def __init__(self) -> None:
        self._handles: dict[str, DraftRunHandle] = {}
        self._lock = threading.Lock()

    def register(
        self,
        *,
        section: str,
        project_id: int,
        cancel_token: CancellationToken,
    ) -> DraftRunHandle:
        handle = DraftRunHandle(
            section=section,
            project_id=project_id,
            cancel_token=cancel_token,
        )
        with self._lock:
            self._handles[section] = handle
        return handle

    def unregister(self, section: str) -> None:
        with self._lock:
            self._handles.pop(section, None)

    def get(self, section: str) -> DraftRunHandle | None:
        with self._lock:
            return self._handles.get(section)

    def get_for_project(self, project_id: int) -> list[DraftRunHandle]:
        with self._lock:
            return [h for h in self._handles.values() if h.project_id == project_id]

    def list_all(self) -> list[DraftRunHandle]:
        with self._lock:
            return list(self._handles.values())

    def reset(self) -> None:
        """Test helper to drop all entries."""
        with self._lock:
            self._handles.clear()


_REGISTRY: DraftRunRegistry | None = None


def get_draft_run_registry() -> DraftRunRegistry:
    """Return the process-shared DraftRunRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = DraftRunRegistry()
    return _REGISTRY
