"""Integration tests for GET chat messages.

Endpoint: ``GET /api/v1/projects/{project_id}/chat/sessions/{session_id}/messages``
"""

from __future__ import annotations

import httpx
import pytest

from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

pytestmark = pytest.mark.integration


def _seed_session(factory, *, project_id: int, title: str = "seed") -> int:
    return ChatSessionRepository(factory).create(project_id=project_id, title=title)


def _seed_messages(factory, *, session_id: int, contents: list[str]) -> list[int]:
    repo = ChatMessageRepository(factory)
    ids: list[int] = []
    for i, c in enumerate(contents):
        role = "user" if i % 2 == 0 else "assistant"
        model = None if role == "user" else "fake-model"
        ids.append(
            repo.append(session_id=session_id, role=role, content=c, model=model)
        )
    return ids


@pytest.mark.asyncio
async def test_empty_session_returns_zero(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"items": [], "total": 0, "offset": 0, "limit": 50}


@pytest.mark.asyncio
async def test_returns_messages_oldest_first_with_full_payload(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    ids = _seed_messages(
        factory, session_id=sid, contents=["first", "reply 1", "second", "reply 2"]
    )

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    items = body["items"]
    # Oldest-first: ids ascending == insertion order.
    assert [i["id"] for i in items] == ids
    assert [i["role"] for i in items] == ["user", "assistant", "user", "assistant"]
    assert [i["content"] for i in items] == ["first", "reply 1", "second", "reply 2"]
    # User turns have model=None; assistant turns carry the model.
    assert items[0]["model"] is None
    assert items[1]["model"] == "fake-model"
    # Each message carries session_id, timestamp (mapped from created_at),
    # and citations is null in v1 (Decision 10).
    for item in items:
        assert item["session_id"] == sid
        assert isinstance(item["timestamp"], str) and item["timestamp"]
        assert item["citations"] is None


@pytest.mark.asyncio
async def test_pagination_offset_and_limit(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    ids = _seed_messages(factory, session_id=sid, contents=[f"m{i}" for i in range(7)])

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        params={"offset": 2, "limit": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 7
    assert body["offset"] == 2
    assert body["limit"] == 3
    assert [i["id"] for i in body["items"]] == ids[2:5]


@pytest.mark.asyncio
async def test_offset_past_total_returns_empty_items(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _seed_messages(factory, session_id=sid, contents=["a", "b"])

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        params={"offset": 100, "limit": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"] == []


@pytest.mark.asyncio
async def test_limit_zero_returns_422(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        params={"limit": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_limit_above_500_returns_422(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        params={"limit": 501},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_session_returns_404(app_client) -> None:
    client, _fid, _rag, _factory, _muth, project_id = app_client
    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/99999/messages"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_session_belonging_to_other_project_returns_404(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    other_sid = _seed_session(factory, project_id=project_id + 1, title="other")
    resp = await client.get(
        f"/api/v1/projects/{project_id}/chat/sessions/{other_sid}/messages"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unknown_project_returns_404(app_client) -> None:
    client, *_ = app_client
    resp = await client.get("/api/v1/projects/99999/chat/sessions/1/messages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(tmp_path) -> None:
    from tests._app_factory import build_test_app

    app = build_test_app(tmp_path, "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://127.0.0.1:12345"
    ) as client:
        resp = await client.get(
            "/api/v1/projects/1/chat/sessions/1/messages",
            headers={"Origin": "https://127.0.0.1:12345"},
        )
    assert resp.status_code == 401
