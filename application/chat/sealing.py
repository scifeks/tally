"""Chat session lifecycle helpers (Phase 8.10).

Two pure application-layer operations that mutate the chat tables:

- :func:`seal_sessions_for_project` — called from
  :class:`application.tools.orchestrator.ScanOrchestrator` after a scan
  completes successfully (Decision 5). Marks every active session for the
  project as expired and then enforces the
  ``chat_session_retention_count`` cap (Decision 6) by hard-deleting the
  oldest expired sessions beyond the cap.
- :func:`purge_chat_for_project` — called from the REPL ``purge`` command
  (Q15). Hard-deletes every chat session (and their messages, via
  ``ON DELETE CASCADE``) for the project regardless of state.

Both helpers construct their repository from a :class:`ProjectPaths` and a
fresh :class:`ConnectionFactory`; they touch no REPL or web concern. They
do not catch their own exceptions — the caller decides whether to suppress
(the orchestrator suppresses so a chat-DB hiccup never masks the scan
result; the REPL surfaces).
"""

from __future__ import annotations

from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository


def seal_sessions_for_project(
    project_id: int,
    *,
    paths: ProjectPaths,
    retention_count: int,
) -> None:
    """Seal active sessions, then sweep expired sessions beyond *retention_count*.

    *retention_count* of 0 disables the sweep but still seals.
    """
    if retention_count < 0:
        raise ValueError("retention_count must be non-negative")
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    repo = ChatSessionRepository(factory)

    active = repo.list_active_for_project(project_id)
    if active:
        repo.mark_expired([row.id for row in active])

    if retention_count == 0:
        return
    for row in repo.select_for_retention(project_id, keep=retention_count):
        repo.delete(row.id)


def purge_chat_for_project(
    project_id: int,
    *,
    paths: ProjectPaths,
) -> int:
    """Hard-delete every chat session for *project_id*; return the count.

    Cascade removes the messages via the FK on ``chat_messages``.
    """
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    repo = ChatSessionRepository(factory)

    rows = repo.list_for_project(project_id, include_expired=True)
    for row in rows:
        repo.delete(row.id)
    return len(rows)
