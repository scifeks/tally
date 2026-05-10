"""Integration tests for POST chat message (start streamed turn).

Endpoint: ``POST /api/v1/projects/{project_id}/chat/sessions/{session_id}/messages``

Uses a fake ``LLMProvider`` and a stubbed ``QueryEngine`` so the test
doesn't need a live ChromaDB.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from application.chat.run_registry import get_chat_run_registry
from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

pytestmark = pytest.mark.integration


# Fakes


class _FakeProvider:
    """Minimal stand-in for ``LLMProvider`` exposing only what 8.8 needs."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.received_messages: list[dict[str, str]] | None = None

    @property
    def model(self) -> str:
        return "fake-chat-model"

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return ""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return ""

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        self.received_messages = list(messages)
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c


class _StubQueryEngine:
    """No-op QueryEngine returning an empty retrieval set."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def search(
        self,
        raw_input: str = "",
        n_results: int = 20,
        query: Any = None,
    ) -> list[dict[str, Any]]:
        del raw_input, n_results, query
        return []


def _seed_session(
    factory, *, project_id: int, title: str = "seed", expired: bool = False
) -> int:
    repo = ChatSessionRepository(factory)
    sid = repo.create(project_id=project_id, title=title)
    if expired:
        repo.mark_expired([sid])
    return sid


def _patch_chat_deps(monkeypatch, *, chunks: list[str]) -> _FakeProvider:
    """Patch the chat handler's stream composer.

    Returns the FakeProvider so tests can inspect what messages it
    received from the chat-service prompt assembly.
    """
    provider = _FakeProvider(chunks)
    fake_composer = SimpleNamespace(
        query_engine=_StubQueryEngine(),
        provider=provider,
        model_name=provider.model,
    )
    monkeypatch.setattr(
        "application.chat.session_service.ChatStreamComposer.for_project",
        lambda registry, cache, base_path, project_id: fake_composer,
    )
    return provider


async def _wait_for_no_active_stream(session_id: int, *, timeout: float = 2.0) -> None:
    """Poll the registry until the background task unregisters itself."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if get_chat_run_registry().get(session_id) is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"chat task for session {session_id} never unregistered")


# Tests


@pytest.fixture(autouse=True)
def _reset_registry():
    get_chat_run_registry().reset()
    yield
    get_chat_run_registry().reset()


@pytest.mark.asyncio
async def test_post_returns_202_with_stream_url(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["hello"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "what's up"},
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["session_id"] == sid
    assert body["assistant_message_id"] is None
    assert isinstance(body["user_message_id"], int)
    assert body["stream_url"] == (
        f"/api/v1/projects/{project_id}/chat/stream?session_id={sid}"
    )

    await _wait_for_no_active_stream(sid)


@pytest.mark.asyncio
async def test_post_persists_user_message_immediately(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["ok"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "first turn"},
        headers=mut_headers,
    )
    assert resp.status_code == 202

    # User row exists right away (write-anchor).
    msgs = ChatMessageRepository(factory).list_for_session(sid)
    user_rows = [m for m in msgs if m.role == "user"]
    assert any(m.content == "first turn" for m in user_rows)

    await _wait_for_no_active_stream(sid)

    # Assistant row appears after the stream completes.
    msgs = ChatMessageRepository(factory).list_for_session(sid)
    assistant_rows = [m for m in msgs if m.role == "assistant"]
    assert len(assistant_rows) == 1
    assert assistant_rows[0].content == "ok"
    assert assistant_rows[0].model == "fake-chat-model"


@pytest.mark.asyncio
async def test_post_409_when_session_expired(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id, expired=True)
    _patch_chat_deps(monkeypatch, chunks=["never"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "hi"},
        headers=mut_headers,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "CHAT_SESSION_EXPIRED"

    # No user row was persisted.
    assert ChatMessageRepository(factory).count_for_session(sid) == 0


@pytest.mark.asyncio
async def test_post_409_when_stream_already_running(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    # Use a provider that yields slowly so the first stream is still in
    # flight when the second POST hits.
    pending = asyncio.Event()
    release = asyncio.Event()

    class _SlowProvider(_FakeProvider):
        async def _iter(self) -> AsyncIterator[str]:
            pending.set()
            await release.wait()
            yield "done"

    provider = _SlowProvider(["done"])
    fake_composer = SimpleNamespace(
        query_engine=_StubQueryEngine(),
        provider=provider,
        model_name=provider.model,
    )
    monkeypatch.setattr(
        "application.chat.session_service.ChatStreamComposer.for_project",
        lambda registry, cache, base_path, project_id: fake_composer,
    )

    first = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "first"},
        headers=mut_headers,
    )
    assert first.status_code == 202

    # Wait for the first stream to actually start before the second POST.
    await asyncio.wait_for(pending.wait(), timeout=2.0)

    second = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "second"},
        headers=mut_headers,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CHAT_STREAM_ALREADY_RUNNING"

    # Let the first stream finish.
    release.set()
    await _wait_for_no_active_stream(sid)


@pytest.mark.asyncio
async def test_post_404_for_unknown_session(app_client, monkeypatch) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    _patch_chat_deps(monkeypatch, chunks=["x"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/99999/messages",
        json={"content": "hi"},
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_404_for_session_in_other_project(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    other_sid = _seed_session(factory, project_id=project_id + 1, title="other")
    _patch_chat_deps(monkeypatch, chunks=["x"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{other_sid}/messages",
        json={"content": "hi"},
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_without_csrf_returns_403(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["x"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "hi"},
        headers={"Origin": "http://127.0.0.1:12345"},
    )
    assert resp.status_code == 403
    assert ChatMessageRepository(factory).count_for_session(sid) == 0


@pytest.mark.asyncio
async def test_post_empty_content_returns_422(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["x"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": ""},
        headers=mut_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_whitespace_only_content_returns_422(
    app_client, monkeypatch
) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["x"])

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "   \n   "},
        headers=mut_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_unauthenticated_returns_401(tmp_path) -> None:
    from tests._app_factory import build_test_app

    app = build_test_app(tmp_path, "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:12345"
    ) as client:
        resp = await client.post(
            "/api/v1/projects/1/chat/sessions/1/messages",
            json={"content": "hi"},
            headers={"Origin": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 401
