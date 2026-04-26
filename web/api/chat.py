"""Phase 8.4 / 8.5 — Chat session endpoints (create + list).

Endpoint surface per ``docs/roadmap/ui-planning/API/endpoints.md §12``:

- ``POST /api/v1/projects/{project_id}/chat/sessions`` (8.4)
- ``GET  /api/v1/projects/{project_id}/chat/sessions`` (8.5)

The send-message, SSE stream, message list, delete, and cancel routes
are Phase 8.6–8.9 and are NOT in this slice.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import (
    ChatSessionRepository,
    ChatSessionRow,
)
from web.api._errors import NotFound
from web.api._project_resolver import _resolve_project
from web.api.schemas import (
    ChatSessionCreateRequest,
    ChatSessionsListResponse,
    ChatSessionSummary,
)

logger = logging.getLogger("tally.web.chat")

v1_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repos(
    row: dict,
) -> tuple[ChatSessionRepository, ChatMessageRepository]:
    paths = ProjectPaths.from_registry_row(row)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return ChatSessionRepository(factory), ChatMessageRepository(factory)


def _row_to_summary(
    row: ChatSessionRow,
    message_repo: ChatMessageRepository,
) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        created_at=row.created_at,
        last_message_at=message_repo.last_created_at(row.id),
        message_count=message_repo.count_for_session(row.id),
        expired_at=row.expired_at,
    )


def _format_title(now: datetime) -> str:
    """Return ``YYYY-MM-DD HH:MM`` for the session title (decisions.md Q15)."""
    return now.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# 8.4 — POST /chat/sessions
# ---------------------------------------------------------------------------


@v1_router.post(
    "/{project_id}/chat/sessions",
    response_model=ChatSessionSummary,
    status_code=201,
)
async def create_chat_session(
    project_id: int,
    request: Request,
    body: ChatSessionCreateRequest | None = None,
) -> ChatSessionSummary:
    """Create a chat session for *project_id*.

    Empty request body in v1; the title is auto-set to the current
    UTC ``YYYY-MM-DD HH:MM`` timestamp (decisions.md B7.4 / Q15).
    """
    del body  # accepted for API symmetry; no fields consumed in v1
    row = _resolve_project(request, project_id)
    session_repo, message_repo = _make_repos(row)
    title = _format_title(datetime.now(UTC))

    session_id = await asyncio.to_thread(
        session_repo.create,
        project_id=project_id,
        title=title,
    )
    fresh = await asyncio.to_thread(session_repo.get, session_id)
    if fresh is None:
        raise NotFound(f"chat session {session_id} not found after creation")
    return _row_to_summary(fresh, message_repo)


# ---------------------------------------------------------------------------
# 8.5 — GET /chat/sessions
# ---------------------------------------------------------------------------


@v1_router.get(
    "/{project_id}/chat/sessions",
    response_model=ChatSessionsListResponse,
)
async def list_chat_sessions(
    project_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> ChatSessionsListResponse:
    """Paginated chat sessions for a project, newest-first.

    Returns one combined list (``items``) covering both active and
    expired sessions; ``expired_at`` distinguishes them so the UI
    can group. Defaults match the findings list (50 / 500).
    """
    row = _resolve_project(request, project_id)
    session_repo, message_repo = _make_repos(row)

    page, total = await asyncio.to_thread(
        session_repo.list_for_project_paginated,
        project_id,
        offset=offset,
        limit=limit,
        include_expired=True,
    )
    items = [_row_to_summary(r, message_repo) for r in page]
    return ChatSessionsListResponse(
        items=items,
        total=total,
        offset=offset,
        limit=limit,
    )
