"""Integration tests for Phase 8.8 — chat SSE event publish contract.

This file covers the chat SSE pipeline by subscribing to the underlying
``EventBus`` directly rather than driving the long-lived SSE endpoint
over HTTP. As the existing ``test_finding_events_sse.py`` documents,
``httpx.AsyncClient`` with ``ASGITransport`` runs the ASGI app inline
on the test event loop, so a long-lived stream blocks any concurrent
POST on the same client. Subscribing to the bus tests the same
publish contract — the ``EventBusChatSink`` field projection and event
ordering — without that constraint. The HTTP wrapper itself is a thin
``StreamingResponse`` that forwards queue items via
``format_sse_frame``; its routing/auth/422 surface is covered by
plain GETs that don't open a long-lived stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from infrastructure.events.bus import EventBus
from infrastructure.events.types import BusEvent
from infrastructure.store.repositories.chat_messages import ChatMessageRepository
from infrastructure.store.repositories.chat_sessions import ChatSessionRepository
from web.adapters.chat_run_registry import get_chat_run_registry

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

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
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        for c in self._chunks:
            # Tiny await so the bus subscriber gets a chance to drain
            # between events; without it the entire stream may publish
            # before the test's queue.get() runs.
            await asyncio.sleep(0)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_session(factory, *, project_id: int, title: str = "seed") -> int:
    return ChatSessionRepository(factory).create(project_id=project_id, title=title)


def _patch_chat_deps(monkeypatch, *, chunks: list[str]) -> None:
    provider = _FakeProvider(chunks)
    fake_composer = SimpleNamespace(
        query_engine=_StubQueryEngine(),
        provider=provider,
        model_name=provider.model,
    )
    monkeypatch.setattr(
        "web.api.chat.ChatStreamComposer.from_request",
        lambda request, project_id: fake_composer,
    )


def _bus_from(client: httpx.AsyncClient) -> EventBus:
    """Reach the EventBus the test app was wired with."""
    return client._transport.app.state.event_bus  # type: ignore[attr-defined]


async def _drain_until_stream_end(
    queue: asyncio.Queue,
    *,
    session_id: int,
    timeout: float = 3.0,
) -> list[BusEvent]:
    """Pull events from *queue* until ``stream_end`` for *session_id*."""
    events: list[BusEvent] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError(
                f"timed out waiting for stream_end on session {session_id}; "
                f"got {[e.event_type for e in events]}"
            )
        item = await asyncio.wait_for(queue.get(), timeout=remaining)
        if not isinstance(item, BusEvent):
            continue
        if item.payload.get("session_id") != session_id:
            continue
        events.append(item)
        if item.event_type == "stream_end":
            return events


async def _wait_for_no_active_stream(session_id: int, *, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if get_chat_run_registry().get(session_id) is None:
            return
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# Tests — bus publish contract via POST → EventBusChatSink
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_registry():
    get_chat_run_registry().reset()
    yield
    get_chat_run_registry().reset()


@pytest.mark.asyncio
async def test_post_drives_stream_start_token_x_n_stream_end(
    app_client, monkeypatch
) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["Hel", "lo,", " world"])

    bus = _bus_from(client)
    sub_id, queue = await bus.subscribe("chat")
    try:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
            json={"content": "what's up"},
            headers=mut_headers,
        )
        assert resp.status_code == 202

        events = await _drain_until_stream_end(queue, session_id=sid)
    finally:
        await bus.unsubscribe("chat", sub_id)

    types = [e.event_type for e in events]
    assert types[0] == "stream_start"
    assert types[-1] == "stream_end"
    assert types.count("token") == 3

    # Token-event chunks preserve order, use §15.4 field name `chunk`
    # (renamed from `token` to avoid the redaction blacklist collision).
    chunks = [e.payload["chunk"] for e in events if e.event_type == "token"]
    assert chunks == ["Hel", "lo,", " world"]

    # stream_end carries assembled content under `content` (Decision 7).
    end = next(e for e in events if e.event_type == "stream_end")
    assert end.payload["content"] == "Hello, world"
    assert end.payload["session_id"] == sid
    assert end.payload["project_id"] == project_id

    await _wait_for_no_active_stream(sid)


@pytest.mark.asyncio
async def test_message_id_populated_on_stream_end_only(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["a", "b"])

    bus = _bus_from(client)
    sub_id, queue = await bus.subscribe("chat")
    try:
        resp = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
            json={"content": "ping"},
            headers=mut_headers,
        )
        assert resp.status_code == 202

        events = await _drain_until_stream_end(queue, session_id=sid)
    finally:
        await bus.unsubscribe("chat", sub_id)

    end = next(e for e in events if e.event_type == "stream_end")
    assert end.payload["message_id"] is not None
    for e in events:
        if e.event_type in ("stream_start", "token"):
            assert e.payload["message_id"] is None

    rows = ChatMessageRepository(factory).list_for_session(sid)
    assistants = [r for r in rows if r.role == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].id == end.payload["message_id"]

    await _wait_for_no_active_stream(sid)


@pytest.mark.asyncio
async def test_streams_for_different_sessions_carry_correct_session_id(
    app_client, monkeypatch
) -> None:
    """The bus publishes both streams' events; payloads keep them apart."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid_a = _seed_session(factory, project_id=project_id, title="a")
    sid_b = _seed_session(factory, project_id=project_id, title="b")
    _patch_chat_deps(monkeypatch, chunks=["x"])

    bus = _bus_from(client)
    sub_id, queue = await bus.subscribe("chat")
    try:
        resp_a = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid_a}/messages",
            json={"content": "a"},
            headers=mut_headers,
        )
        assert resp_a.status_code == 202
        events_a = await _drain_until_stream_end(queue, session_id=sid_a)

        resp_b = await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid_b}/messages",
            json={"content": "b"},
            headers=mut_headers,
        )
        assert resp_b.status_code == 202
        events_b = await _drain_until_stream_end(queue, session_id=sid_b)
    finally:
        await bus.unsubscribe("chat", sub_id)

    assert all(e.payload["session_id"] == sid_a for e in events_a)
    assert all(e.payload["session_id"] == sid_b for e in events_b)

    await _wait_for_no_active_stream(sid_a)
    await _wait_for_no_active_stream(sid_b)


@pytest.mark.asyncio
async def test_event_bus_payload_carries_filter_fields(app_client, monkeypatch) -> None:
    """All non-snapshot events carry session_id + project_id for SSE filter."""
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    sid = _seed_session(factory, project_id=project_id)
    _patch_chat_deps(monkeypatch, chunks=["hi"])

    bus = _bus_from(client)
    sub_id, queue = await bus.subscribe("chat")
    try:
        await client.post(
            f"/api/v1/projects/{project_id}/chat/sessions/{sid}/messages",
            json={"content": "x"},
            headers=mut_headers,
        )
        events = await _drain_until_stream_end(queue, session_id=sid)
    finally:
        await bus.unsubscribe("chat", sub_id)

    for e in events:
        assert e.stream == "chat"
        assert e.job_id == "chat"
        assert e.payload["session_id"] == sid
        assert e.payload["project_id"] == project_id

    await _wait_for_no_active_stream(sid)


# ---------------------------------------------------------------------------
# Tests — HTTP-only paths (no streaming open) — safe with ASGITransport
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_missing_session_id_returns_422(app_client) -> None:
    client, *_ = app_client
    resp = await client.get("/api/v1/projects/1/chat/stream")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_stream_unauthenticated_returns_401(tmp_path) -> None:
    from web.server import create_app

    app = create_app(str(tmp_path), "test-handshake-abc123xyz", port=12345)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1:12345"
    ) as client:
        resp = await client.get(
            "/api/v1/projects/1/chat/stream",
            params={"session_id": 1},
            headers={"Origin": "http://127.0.0.1:12345"},
        )
    assert resp.status_code == 401
