"""Helpers to seal and purge chat sessions.

Two pure application-layer operations that mutate the chat tables:

- :func:`seal_sessions_for_project`: called from
  :class:`application.tools.orchestrator.ScanOrchestrator` after scan
  success. Marks every active session as expired and enforces the
  ``chat_session_retention_count`` cap by hard-deleting the oldest
  expired sessions beyond the cap.
- :func:`purge_chat_for_project`: called from the REPL ``purge`` command.
  Hard-deletes every chat session and their messages (via
  ``ON DELETE CASCADE``) for the project regardless of state.

Both helpers operate on a caller-supplied
:class:`ChatSessionRepositoryPort`; construction of the concrete
repository is the composition root's responsibility (the REPL command,
the orchestrator, or a test fixture). They do not catch their own
exceptions; the caller decides whether to suppress (the orchestrator
suppresses so a chat-DB hiccup never masks the scan result; the REPL
surfaces).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.chat_session_repository import (
        ChatSessionRepositoryPort,
    )


def seal_sessions_for_project(
    project_id: int,
    *,
    session_repo: ChatSessionRepositoryPort,
    retention_count: int,
) -> None:
    """Seal active sessions, then sweep expired sessions beyond *retention_count*.

    *retention_count* of 0 disables the sweep but still seals.
    """
    if retention_count < 0:
        raise ValueError("retention_count must be non-negative")

    active = session_repo.list_active_for_project(project_id)
    if active:
        session_repo.mark_expired([row.id for row in active])

    if retention_count == 0:
        return
    for row in session_repo.select_for_retention(project_id, keep=retention_count):
        session_repo.delete(row.id)


def purge_chat_for_project(
    project_id: int,
    *,
    session_repo: ChatSessionRepositoryPort,
) -> int:
    """Hard-delete every chat session for *project_id*; return the count.

    Cascade removes the messages via the FK on ``chat_messages``.
    """
    rows = session_repo.list_for_project(project_id, include_expired=True)
    for row in rows:
        session_repo.delete(row.id)
    return len(rows)
