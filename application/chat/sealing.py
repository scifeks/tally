"""Seal and purge chat sessions for a project."""

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


def seal_sessions_by_mode(
    project_id: int,
    *,
    mode: str,
    session_repo: ChatSessionRepositoryPort,
) -> int:
    """Seal active sessions matching *mode* for *project_id*."""
    active = session_repo.list_active_for_project(project_id)
    matching = [row for row in active if row.mode == mode]
    if matching:
        session_repo.mark_expired([row.id for row in matching])
    return len(matching)


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
