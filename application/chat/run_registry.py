"""Process-singleton tracking active chat streams."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatRunHandle:
    session_id: int
    project_id: int
    user_message_id: int
    task: asyncio.Task[None]


class ChatRunRegistry:
    """Process-singleton map of session_id -> ChatRunHandle."""

    def __init__(self) -> None:
        self._handles: dict[int, ChatRunHandle] = {}
        self._lock = threading.Lock()

    def register(
        self,
        *,
        session_id: int,
        project_id: int,
        user_message_id: int,
        task: asyncio.Task[None],
    ) -> ChatRunHandle:
        handle = ChatRunHandle(
            session_id=session_id,
            project_id=project_id,
            user_message_id=user_message_id,
            task=task,
        )
        with self._lock:
            self._handles[session_id] = handle
        return handle

    def unregister(self, session_id: int) -> None:
        with self._lock:
            self._handles.pop(session_id, None)

    def get(self, session_id: int) -> ChatRunHandle | None:
        with self._lock:
            return self._handles.get(session_id)

    def list_for_project(self, project_id: int) -> list[ChatRunHandle]:
        with self._lock:
            return [h for h in self._handles.values() if h.project_id == project_id]

    def list_all(self) -> list[ChatRunHandle]:
        with self._lock:
            return list(self._handles.values())

    def reset(self) -> None:
        """Test helper to drop all entries."""
        with self._lock:
            self._handles.clear()


_REGISTRY: ChatRunRegistry | None = None


def get_chat_run_registry() -> ChatRunRegistry:
    """Return the process-shared ChatRunRegistry."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ChatRunRegistry()
    return _REGISTRY
