"""Integration tests for the Phase 8.2 application-layer chat service.

Uses a real SQLite-backed ``ChatSessionRepository`` /
``ChatMessageRepository`` plus a fake ``LLMProvider`` that yields a
scripted token stream. Retrieval is exercised through a fake
``QueryEngine`` so we don't need a real ChromaDB instance — the test
focus is the service's orchestration, not the RAG pipeline.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.chat.service import (  # noqa: E402
    PROMPT_CHAR_CEILING,
    ChatRequest,
    ChatSessionExpired,
    ChatSessionNotFound,
    stream_chat,
)
from application.ports.chat_event_sink import ChatStreamSink  # noqa: E402
from core.llm.base import LLMAdapterError, LLMProvider  # noqa: E402
from domain.pipeline.chat_events import (  # noqa: E402
    ChatEvent,
    ChatStreamCancelled,
    ChatStreamCompleted,
    ChatStreamFailed,
    ChatStreamStarted,
    ChatToken,
)
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.chat_messages import (  # noqa: E402
    ChatMessageRepository,
)
from infrastructure.store.repositories.chat_sessions import (  # noqa: E402
    ChatSessionRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeProvider(LLMProvider):
    """LLMProvider that yields a pre-scripted token stream."""

    def __init__(
        self,
        chunks: list[str],
        *,
        raise_after: int | None = None,
    ) -> None:
        self.chunks = list(chunks)
        self.raise_after = raise_after
        self.received_messages: list[dict[str, str]] | None = None
        self.call_count = 0

    @property
    def model(self) -> str:
        return "fake-provider-model"

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
        self.call_count += 1
        return self._iter_chunks()

    async def _iter_chunks(self) -> AsyncIterator[str]:
        for i, chunk in enumerate(self.chunks):
            if self.raise_after is not None and i >= self.raise_after:
                raise LLMAdapterError("scripted failure")
            yield chunk


class FakeQueryEngine:
    """Stand-in for ``QueryEngine`` exposing only ``search``."""

    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results or []
        self.calls: list[tuple[str, int]] = []

    def search(
        self,
        raw_input: str = "",
        n_results: int = 20,
        query: Any = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((raw_input, n_results))
        return list(self.results)


class CapturingSink(ChatStreamSink):
    """Records every emitted event in order."""

    def __init__(self) -> None:
        self.events: list[ChatEvent] = []

    def emit(self, event: ChatEvent) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "tally.db")
    f.init_schema()
    return f


@pytest.fixture()
def session_repo(factory: ConnectionFactory) -> ChatSessionRepository:
    return ChatSessionRepository(factory)


@pytest.fixture()
def message_repo(factory: ConnectionFactory) -> ChatMessageRepository:
    return ChatMessageRepository(factory)


@pytest.fixture()
def seed_session(session_repo: ChatSessionRepository) -> int:
    return session_repo.create(project_id=42, title="2026-04-25 14:30")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_streams_tokens_and_persists_assistant_turn(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    provider = FakeProvider(["Hel", "lo,", " world"])
    qe = FakeQueryEngine(
        [{"document": "SQLi finding", "metadata": {"tool": "semgrep"}}]
    )
    sink = CapturingSink()
    request = ChatRequest(
        session_id=seed_session, project_id=42, user_message="What's there?"
    )

    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=qe,
        provider=provider,
        model_name="fake-model-v1",
        event_sink=sink,
    )
    chunks = [c async for c in gen]

    assert chunks == ["Hel", "lo,", " world"]

    rows = message_repo.list_for_session(seed_session)
    assert [r.role for r in rows] == ["user", "assistant"]
    assert rows[0].content == "What's there?"
    assert rows[0].model is None
    assert rows[1].content == "Hello, world"
    assert rows[1].model == "fake-model-v1"

    types = [type(e) for e in sink.events]
    assert types[0] is ChatStreamStarted
    assert types[-1] is ChatStreamCompleted
    assert all(t is ChatToken for t in types[1:-1])
    assert len(types) == 5  # start + 3 tokens + completed
    assert isinstance(sink.events[-1], ChatStreamCompleted)
    assert sink.events[-1].assistant_message_id == rows[1].id


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_called_with_user_message_and_top_n(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    provider = FakeProvider(["ok"])
    qe = FakeQueryEngine(
        [{"document": "Critical RCE", "metadata": {"tool": "zap", "profile": "web"}}]
    )
    request = ChatRequest(
        session_id=seed_session, project_id=42, user_message="Audit the API"
    )

    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=qe,
        provider=provider,
    )
    [c async for c in gen]

    assert qe.calls == [("Audit the API", 20)]
    assert provider.received_messages is not None
    system_msg = provider.received_messages[0]
    assert system_msg["role"] == "system"
    assert "Critical RCE" in system_msg["content"]
    assert "[zap repo=web]" in system_msg["content"]
    last_msg = provider.received_messages[-1]
    assert last_msg == {"role": "user", "content": "Audit the API"}


@pytest.mark.asyncio
async def test_retrieval_failure_falls_back_to_no_context(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    provider = FakeProvider(["ok"])

    class _BoomQE:
        def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            raise RuntimeError("chroma down")

    request = ChatRequest(session_id=seed_session, project_id=42, user_message="Hi")
    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=_BoomQE(),  # type: ignore[arg-type]
        provider=provider,
    )
    [c async for c in gen]

    assert provider.received_messages is not None
    assert "(no findings retrieved)" in provider.received_messages[0]["content"]


# ---------------------------------------------------------------------------
# Prompt assembly + 500k ceiling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_assembly_trims_prior_turns_above_ceiling(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    big = "x" * 100_000
    for i in range(8):
        message_repo.append(
            session_id=seed_session,
            role="user" if i % 2 == 0 else "assistant",
            content=big,
            model=None if i % 2 == 0 else "old-model",
        )

    provider = FakeProvider(["ok"])
    request = ChatRequest(
        session_id=seed_session, project_id=42, user_message="What now?"
    )

    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=FakeQueryEngine(),
        provider=provider,
    )
    [c async for c in gen]

    assert provider.received_messages is not None
    total = sum(len(m["content"]) for m in provider.received_messages)
    assert total <= PROMPT_CHAR_CEILING
    assert provider.received_messages[0]["role"] == "system"
    assert provider.received_messages[-1] == {
        "role": "user",
        "content": "What now?",
    }
    # Some prior turns must have been dropped given the ceiling.
    assert len(provider.received_messages) < 11  # system + 8 prior + new user

    # Stored rows are untouched at trim time: the 8 prior rows are still
    # present after the trim, plus the new user + assistant rows persisted
    # by this turn = 10 total.
    persisted = message_repo.list_for_session(seed_session)
    assert len(persisted) == 10
    assert all(r.content == big for r in persisted[:8])


@pytest.mark.asyncio
async def test_prior_turns_passed_to_provider_in_order(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    message_repo.append(session_id=seed_session, role="user", content="first user")
    message_repo.append(
        session_id=seed_session,
        role="assistant",
        content="first reply",
        model="m",
    )

    provider = FakeProvider(["ok"])
    request = ChatRequest(
        session_id=seed_session, project_id=42, user_message="follow up"
    )
    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=FakeQueryEngine(),
        provider=provider,
    )
    [c async for c in gen]

    assert provider.received_messages is not None
    roles_and_content = [(m["role"], m["content"]) for m in provider.received_messages]
    # system + 2 prior + new user
    assert roles_and_content[0][0] == "system"
    assert roles_and_content[1] == ("user", "first user")
    assert roles_and_content[2] == ("assistant", "first reply")
    assert roles_and_content[3] == ("user", "follow up")


# ---------------------------------------------------------------------------
# Cancellation: aclose() does not persist assistant row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aclose_after_partial_stream_does_not_persist_assistant(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    provider = FakeProvider(["par", "tial", " response"])
    sink = CapturingSink()
    request = ChatRequest(session_id=seed_session, project_id=42, user_message="go")

    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=FakeQueryEngine(),
        provider=provider,
        event_sink=sink,
    )
    iterator = gen.__aiter__()
    first = await iterator.__anext__()
    assert first == "par"
    await gen.aclose()  # type: ignore[union-attr]

    rows = message_repo.list_for_session(seed_session)
    assert [r.role for r in rows] == ["user"]
    assert rows[0].content == "go"

    assert any(isinstance(e, ChatStreamCancelled) for e in sink.events)
    assert not any(isinstance(e, ChatStreamCompleted) for e in sink.events)


# ---------------------------------------------------------------------------
# Provider error: assistant turn not persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_error_does_not_persist_assistant(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    provider = FakeProvider(["ok ", "so far"], raise_after=1)
    sink = CapturingSink()
    request = ChatRequest(session_id=seed_session, project_id=42, user_message="hi")

    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=FakeQueryEngine(),
        provider=provider,
        event_sink=sink,
    )
    with pytest.raises(LLMAdapterError):
        [c async for c in gen]

    rows = message_repo.list_for_session(seed_session)
    assert [r.role for r in rows] == ["user"]

    failures = [e for e in sink.events if isinstance(e, ChatStreamFailed)]
    assert len(failures) == 1
    assert failures[0].error == "LLMAdapterError"


# ---------------------------------------------------------------------------
# Validation: expired & wrong project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_session_raises_before_persistence(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    session_repo.mark_expired([seed_session])
    provider = FakeProvider(["never"])
    request = ChatRequest(session_id=seed_session, project_id=42, user_message="hi")

    with pytest.raises(ChatSessionExpired):
        await stream_chat(
            request,
            session_repo=session_repo,
            message_repo=message_repo,
            query_engine=FakeQueryEngine(),
            provider=provider,
        )

    assert message_repo.list_for_session(seed_session) == []
    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_wrong_project_raises_not_found(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    provider = FakeProvider(["never"])
    request = ChatRequest(session_id=seed_session, project_id=999, user_message="hi")

    with pytest.raises(ChatSessionNotFound):
        await stream_chat(
            request,
            session_repo=session_repo,
            message_repo=message_repo,
            query_engine=FakeQueryEngine(),
            provider=provider,
        )

    assert message_repo.list_for_session(seed_session) == []
    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_unknown_session_raises_not_found(
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
) -> None:
    provider = FakeProvider(["never"])
    request = ChatRequest(session_id=99999, project_id=42, user_message="hi")

    with pytest.raises(ChatSessionNotFound):
        await stream_chat(
            request,
            session_repo=session_repo,
            message_repo=message_repo,
            query_engine=FakeQueryEngine(),
            provider=provider,
        )

    assert provider.call_count == 0


# ---------------------------------------------------------------------------
# Bookkeeping: session.touch fires on success only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_touched_on_completion(
    factory: ConnectionFactory,
    session_repo: ChatSessionRepository,
    message_repo: ChatMessageRepository,
    seed_session: int,
) -> None:
    before = session_repo.get(seed_session)
    assert before is not None
    original_updated_at = before.updated_at

    # Touch the row backwards in time so we can detect a re-touch.
    with factory.connect() as conn:
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", seed_session),
        )

    provider = FakeProvider(["done"])
    request = ChatRequest(session_id=seed_session, project_id=42, user_message="ping")
    gen = await stream_chat(
        request,
        session_repo=session_repo,
        message_repo=message_repo,
        query_engine=FakeQueryEngine(),
        provider=provider,
    )
    [c async for c in gen]

    after = session_repo.get(seed_session)
    assert after is not None
    assert after.updated_at != "2000-01-01T00:00:00+00:00"
    assert after.updated_at >= original_updated_at
