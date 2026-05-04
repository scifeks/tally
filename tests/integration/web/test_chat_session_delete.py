"""Integration tests for DELETE chat session.

Endpoint: ``DELETE /api/v1/projects/{project_id}/chat/sessions/{session_id}``
"""

from __future__ import annotations

import httpx
import pytest

from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

pytestmark = pytest.mark.integration


def _seed_session(factory, *, project_id: int, title: str = "seed") -> int:
    return ChatSessionRepository(factory).create(project_id=project_id, title=title)


@pytest.mark.asyncio
async def test_delete_returns_204(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}",
        headers=mut_headers,
    )
    assert resp.status_code == 204, resp.text
    # Body is empty.
    assert resp.content == b""

    # Session row is gone.
    assert ChatSessionRepository(factory).get(sid) is None


@pytest.mark.asyncio
async def test_delete_cascades_to_messages(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    msgs = ChatMessageRepository(factory)
    msgs.append(session_id=sid, role="user", content="hello")
    msgs.append(session_id=sid, role="assistant", content="hi", model="m")
    assert msgs.count_for_session(sid) == 2

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}",
        headers=mut_headers,
    )
    assert resp.status_code == 204

    # FK cascade removed all messages for the session.
    assert msgs.count_for_session(sid) == 0


@pytest.mark.asyncio
async def test_delete_unknown_session_returns_404(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/chat/sessions/99999",
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_for_other_project_returns_404(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    other_sid = _seed_session(factory, project_id=project_id + 1, title="other")

    resp = await client.delete(
        f"/api/v1/projects/{project_id}/chat/sessions/{other_sid}",
        headers=mut_headers,
    )
    assert resp.status_code == 404
    # The session row for the other project must NOT have been deleted.
    assert ChatSessionRepository(factory).get(other_sid) is not None


@pytest.mark.asyncio
async def test_delete_without_csrf_returns_403(app_client) -> None:
    client, _fid, _rag, factory, _mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    # Authenticated cookies are present, but no X-CSRF-Token header.
    resp = await client.delete(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}",
        headers={"Origin": "http://127.0.0.1:12345"},
    )
    assert resp.status_code == 403, resp.text
    # Session is untouched.
    assert ChatSessionRepository(factory).get(sid) is not None


@pytest.mark.asyncio
async def test_delete_unauthenticated_returns_401(tmp_path) -> None:
    from tests._app_factory import build_test_app

    app = build_test_app(tmp_path, "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:12345"
    ) as client:
        resp = await client.delete(
            "/api/v1/projects/1/chat/sessions/1",
            headers={"Origin": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 401
