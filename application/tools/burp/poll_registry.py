"""Track active Burp Organizer poll runs."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from application.locking.cancellation import CancellationToken


@dataclass(frozen=True)
class BurpPollHandle:
    project_id: int
    cancel_token: CancellationToken


class BurpPollRunRegistry:
    """Process-singleton map of project_id -> BurpPollHandle."""

    def __init__(self) -> None:
        self._handles: dict[int, BurpPollHandle] = {}
        self._lock = threading.Lock()

    def register(
        self,
        *,
        project_id: int,
        cancel_token: CancellationToken,
    ) -> BurpPollHandle:
        handle = BurpPollHandle(
            project_id=project_id,
            cancel_token=cancel_token,
        )
        with self._lock:
            self._handles[project_id] = handle
        return handle

    def unregister(self, project_id: int) -> None:
        with self._lock:
            self._handles.pop(project_id, None)

    def get_for_project(self, project_id: int) -> BurpPollHandle | None:
        with self._lock:
            return self._handles.get(project_id)

    def reset(self) -> None:
        with self._lock:
            self._handles.clear()


_REGISTRY: BurpPollRunRegistry | None = None


def get_burp_poll_registry() -> BurpPollRunRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = BurpPollRunRegistry()
    return _REGISTRY
