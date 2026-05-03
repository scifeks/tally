"""Integration tests for POST chat session cancel.

Endpoint: ``POST /api/v1/projects/{project_id}/chat/sessions/{session_id}/cancel``

The cancel endpoint looks up the in-flight asyncio task in the chat run
registry and calls ``task.cancel()``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from application.chat.run_registry import get_chat_run_registry
from infrastructure.events.types import EOS
from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository

pytestmark = pytest.mark.integration


# Fakes (mirror tests/integration/web/test_chat_message_send.py)


class _FakeProvider:
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


def _seed_session(factory, *, project_id: int, title: str = "seed") -> int:
    repo = ChatSessionRepository(factory)
    return repo.create(project_id=project_id, title=title)


def _patch_chat_deps(monkeypatch, *, provider: _FakeProvider) -> None:
    fake_composer = SimpleNamespace(
        query_engine=_StubQueryEngine(),
        provider=provider,
        model_name=provider.model,
    )
    monkeypatch.setattr(
        "application.chat.session_service.ChatStreamComposer.for_project",
        lambda registry, cache, base_path, project_id: fake_composer,
    )


async def _wait_for_no_active_stream(session_id: int, *, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if get_chat_run_registry().get(session_id) is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"chat task for session {session_id} never unregistered")


@pytest.fixture(autouse=True)
def _reset_registry():
    get_chat_run_registry().reset()
    yield
    get_chat_run_registry().reset()


# Tests


@pytest.mark.asyncio
async def test_cancel_returns_202_for_active_stream(app_client, monkeypatch) -> None:
    """A live stream cancels with 202 and the documented payload shape."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    release = asyncio.Event()
    started = asyncio.Event()

    class _SlowProvider(_FakeProvider):
        async def _iter(self) -> AsyncIterator[str]:
            started.set()
            await release.wait()
            yield "late"

    provider = _SlowProvider(["late"])
    _patch_chat_deps(monkeypatch, provider=provider)

    post = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
        json={"content": "go"},
        headers=mut_headers,
    )
    assert post.status_code == 202
    await asyncio.wait_for(started.wait(), timeout=2.0)

    cancel = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/cancel",
        headers=mut_headers,
    )
    assert cancel.status_code == 202, cancel.text
    body = cancel.json()
    assert body == {
        "session_id": sid,
        "cancelled_message_id": None,
    }

    # Allow the cancelled stream to wind down. The driver's finally
    # unregisters the handle even though the iterator is now exhausted /
    # the task is cancelled.
    release.set()
    await _wait_for_no_active_stream(sid)


@pytest.mark.asyncio
async def test_cancel_emits_stream_cancelled_and_skips_persist(
    app_client, monkeypatch
) -> None:
    """End-to-end: bus emits stream_cancelled and the assistant row is absent."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)

    started = asyncio.Event()

    class _BlockingProvider(_FakeProvider):
        async def _iter(self) -> AsyncIterator[str]:
            started.set()
            # Yield nothing and block forever until cancelled.
            await asyncio.Event().wait()
            yield "never"  # pragma: no cover

    provider = _BlockingProvider([])
    _patch_chat_deps(monkeypatch, provider=provider)

    bus = client._transport.app.state.event_bus  # type: ignore[union-attr,attr-defined]
    sub_id, queue = await bus.subscribe("chat")

    try:
        post = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
            json={"content": "go"},
            headers=mut_headers,
        )
        assert post.status_code == 202
        await asyncio.wait_for(started.wait(), timeout=2.0)

        cancel = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid}/cancel",
            headers=mut_headers,
        )
        assert cancel.status_code == 202

        # Drain bus events until we see stream_cancelled (or timeout).
        deadline = asyncio.get_event_loop().time() + 2.0
        seen_types: list[str] = []
        while asyncio.get_event_loop().time() < deadline:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            if item is EOS:
                break
            seen_types.append(item.event_type)
            if item.event_type == "stream_cancelled":
                assert item.payload["session_id"] == sid
                assert item.payload["project_id"] == project_id
                assert item.payload["message_id"] is None
                break
        else:
            raise AssertionError(f"never saw stream_cancelled; saw: {seen_types}")

        await _wait_for_no_active_stream(sid)

        # No assistant row should have been persisted (decisions.md B7.7).
        msgs = ChatMessageRepository(factory).list_for_session(sid)
        roles = [m.role for m in msgs]
        assert "user" in roles
        assert "assistant" not in roles
    finally:
        await bus.unsubscribe("chat", sub_id)


@pytest.mark.asyncio
async def test_cancel_409_when_no_active_stream(app_client, monkeypatch) -> None:
    """A session with no in-flight task returns 409 CHAT_NO_ACTIVE_STREAM."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    del monkeypatch  # no provider patching needed; we never POST a message

    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"]["code"] == "CHAT_NO_ACTIVE_STREAM"
    assert body["error"]["details"] == {"session_id": sid}


@pytest.mark.asyncio
async def test_cancel_404_for_unknown_session(app_client) -> None:
    client, _fid, _rag, _factory, mut_headers, project_id = app_client
    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/99999/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_404_for_session_in_other_project(app_client) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    other_sid = _seed_session(factory, project_id=project_id + 1, title="other")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{other_sid}/cancel",
        headers=mut_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_without_csrf_returns_403(app_client) -> None:
    client, _fid, _rag, factory, _muth, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    resp = await client.post(
        f"/api/v1/projects/{project_id}/chat/sessions/{sid}/cancel",
        headers={"Origin": "http://127.0.0.1:12345"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cancel_unauthenticated_returns_401(tmp_path) -> None:
    from web.server import create_app

    app = create_app(str(tmp_path), "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:12345"
    ) as client:
        resp = await client.post(
            "/api/v1/projects/1/chat/sessions/1/cancel",
            headers={"Origin": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 401
