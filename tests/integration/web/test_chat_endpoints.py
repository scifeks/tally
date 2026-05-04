"""Integration tests for chat session endpoints.

Covers:

- ``POST /api/v1/projects/{id}/chat/sessions``: auth, CSRF, title.
- ``GET  /api/v1/projects/{id}/chat/sessions``: pagination, ordering.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx
import pytest

from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

pytestmark = pytest.mark.integration


_TITLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def _seed_session(
    factory,
    *,
    project_id: int,
    title: str = "seed",
    expired: bool = False,
) -> int:
    repo = ChatSessionRepository(factory)
    sid = repo.create(project_id=project_id, title=title)
    if expired:
        repo.mark_expired([sid])
    return sid


# POST /chat/sessions  (8.4)


@pytest.mark.asyncio
async def test_create_session_201_with_timestamp_title(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client

    before = datetime.now(UTC)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions",
        json={},
        headers=mut_headers,
    )
    after = datetime.now(UTC)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["project_id"] == project_id
    assert body["expired_at"] is None
    assert body["message_count"] == 0
    assert body["last_message_at"] is None
    assert _TITLE_RE.match(body["title"]), body["title"]

    # Title should be within the same UTC minute as the request window.
    title_dt = datetime.strptime(body["title"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    assert before.replace(second=0, microsecond=0) <= title_dt
    assert title_dt <= after.replace(second=0, microsecond=0)


@pytest.mark.asyncio
async def test_create_session_persists_row(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions",
        json={},
        headers=mut_headers,
    )
    assert resp.status_code == 201
    sid = resp.json()["id"]
    repo = ChatSessionRepository(factory)
    row = repo.get(sid)
    assert row is not None
    assert row.project_id == project_id
    assert row.expired_at is None


@pytest.mark.asyncio
async def test_create_session_unknown_project_returns_404(app_client) -> None:
    client, *_, mut_headers, _project_id = app_client
    resp = await client.post(
        "/api/v1/projects/99999/chat/sessions",
        json={},
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_session_without_csrf_is_forbidden(app_client) -> None:
    client, *_, project_id = app_client
    # Authenticated cookies are present from the fixture, but no X-CSRF-Token.
    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions",
        json={},
        headers={"Origin": "http://127.0.0.1:12345"},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_create_session_unauthenticated_is_unauthorized(tmp_path) -> None:
    """A fresh client with no session cookie must be rejected."""
    from tests._app_factory import build_test_app

    app = build_test_app(tmp_path, "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:12345",
    ) as client:
        resp = await client.post(
            "/api/v1/projects/1/chat/sessions",
            json={},
            headers={"Origin": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 401


# GET /chat/sessions  (8.5)


@pytest.mark.asyncio
async def test_list_empty_returns_200(app_client) -> None:
    client, *_, project_id = app_client
    resp = await client.get(f"/api/v1/projects/{project_id}/chat/sessions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"items": [], "total": 0, "offset": 0, "limit": 50}


@pytest.mark.asyncio
async def test_list_returns_active_and_expired_newest_first(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    a = _seed_session(factory, project_id=project_id, title="oldest")
    b = _seed_session(factory, project_id=project_id, title="middle", expired=True)
    c = _seed_session(factory, project_id=project_id, title="newest")

    resp = await client.get(f"/api/v1/projects/{project_id}/chat/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    ids = [item["id"] for item in body["items"]]
    assert ids == [c, b, a]

    # The expired session is in the same list, distinguished by expired_at.
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id[b]["expired_at"] is not None
    assert by_id[a]["expired_at"] is None
    assert by_id[c]["expired_at"] is None


@pytest.mark.asyncio
async def test_list_pagination(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    ids = [
        _seed_session(factory, project_id=project_id, title=f"s{i}") for i in range(5)
    ]
    # Newest-first: ids[4], ids[3], ids[2], ids[1], ids[0]

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions",
        params={"offset": 1, "limit": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["offset"] == 1
    assert body["limit"] == 2
    item_ids = [i["id"] for i in body["items"]]
    assert item_ids == [ids[3], ids[2]]


@pytest.mark.asyncio
async def test_list_limit_above_total_returns_all(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    for i in range(3):
        _seed_session(factory, project_id=project_id, title=f"s{i}")

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions",
        params={"limit": 100},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["limit"] == 100


@pytest.mark.asyncio
async def test_list_unknown_project_returns_404(app_client) -> None:
    client, *_ = app_client
    resp = await client.get("/api/v1/projects/99999/chat/sessions")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_unauthenticated_is_unauthorized(tmp_path) -> None:
    from tests._app_factory import build_test_app

    app = build_test_app(tmp_path, "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1:12345",
    ) as client:
        resp = await client.get(
            "/api/v1/projects/1/chat/sessions",
            headers={"Origin": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_returns_message_count_and_last_message_at(app_client) -> None:
    """Session summary derives ``message_count`` and ``last_message_at``."""
    from infrastructure.store.repositories.chat_messages import (
        ChatMessageRepository,
    )

    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id, title="active")
    msgs = ChatMessageRepository(factory)
    msgs.append(session_id=sid, role="user", content="hi")
    msgs.append(session_id=sid, role="assistant", content="yo", model="m")

    resp = await client.get(f"/api/v1/projects/{project_id}/chat/sessions")
    body = resp.json()
    item = next(i for i in body["items"] if i["id"] == sid)
    assert item["message_count"] == 2
    assert item["last_message_at"] is not None
