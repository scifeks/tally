"""Unit tests for ``application.chat.session_service.ChatSessionService``."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.chat.run_registry import get_chat_run_registry
from application.chat.service import (
    ChatSessionExpired,
    ChatSessionNotFound,
    ChatStreamAlreadyRunning,
    ChatStreamNotRunning,
)
from application.chat.session_service import (
    ChatSessionService,
    ProjectNotFound,
    SendMessageHandle,
)
from domain.chat.entry import ChatMessageRow, ChatSessionRow
from domain.projects.entry import ProjectRow


class _StubSessionRepo:
    def __init__(self, rows: dict[int, ChatSessionRow] | None = None) -> None:
        self.rows: dict[int, ChatSessionRow] = dict(rows or {})
        self._next_id = max(self.rows, default=0) + 1
        self.create_calls: list[dict[str, Any]] = []
        self.delete_calls: list[int] = []
        self.list_calls: list[dict[str, Any]] = []
        self.list_return: tuple[list[ChatSessionRow], int] = ([], 0)
        self.suppress_re_fetch = False

    def create(self, *, project_id: int, title: str) -> int:
        new_id = self._next_id
        self._next_id += 1
        self.create_calls.append({"project_id": project_id, "title": title})
        if not self.suppress_re_fetch:
            self.rows[new_id] = ChatSessionRow(
                id=new_id,
                project_id=project_id,
                title=title,
                created_at="2026-05-02T00:00:00Z",
                updated_at="2026-05-02T00:00:00Z",
                expired_at=None,
            )
        return new_id

    def get(self, session_id: int) -> ChatSessionRow | None:
        return self.rows.get(session_id)

    def delete(self, session_id: int) -> None:
        self.delete_calls.append(session_id)
        self.rows.pop(session_id, None)

    def list_for_project_paginated(
        self,
        project_id: int,
        *,
        offset: int,
        limit: int,
        include_expired: bool = True,
    ) -> tuple[list[ChatSessionRow], int]:
        self.list_calls.append(
            {
                "project_id": project_id,
                "offset": offset,
                "limit": limit,
                "include_expired": include_expired,
            }
        )
        return self.list_return

    def touch(self, session_id: int, when: str | None = None) -> None:
        del session_id, when

    def mark_expired(self, session_ids: Iterable[int], when: str | None = None) -> None:
        del session_ids, when

    def list_for_project(
        self, project_id: int, *, include_expired: bool = True
    ) -> list[ChatSessionRow]:
        del project_id, include_expired
        return []

    def list_active_for_project(self, project_id: int) -> list[ChatSessionRow]:
        del project_id
        return []

    def list_expired_for_project(self, project_id: int) -> list[ChatSessionRow]:
        del project_id
        return []

    def select_for_retention(
        self, project_id: int, *, keep: int
    ) -> list[ChatSessionRow]:
        del project_id, keep
        return []


class _StubMessageRepo:
    def __init__(self) -> None:
        self.append_calls: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []
        self.list_return: tuple[list[ChatMessageRow], int] = ([], 0)
        self.last_at: str | None = None
        self.count: int = 0

    def append(
        self,
        *,
        session_id: int,
        role: str,
        content: str,
        model: str | None = None,
    ) -> int:
        self.append_calls.append(
            {
                "session_id": session_id,
                "role": role,
                "content": content,
                "model": model,
            }
        )
        return 99

    def list_for_session_paginated(
        self,
        session_id: int,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ChatMessageRow], int]:
        self.list_calls.append(
            {"session_id": session_id, "offset": offset, "limit": limit}
        )
        return self.list_return

    def count_for_session(self, session_id: int) -> int:
        del session_id
        return self.count

    def last_created_at(self, session_id: int) -> str | None:
        del session_id
        return self.last_at

    def list_for_session(self, session_id: int) -> list[ChatMessageRow]:
        del session_id
        return []


def _row(
    session_id: int, project_id: int, *, expired: str | None = None
) -> ChatSessionRow:
    return ChatSessionRow(
        id=session_id,
        project_id=project_id,
        title="t",
        created_at="2026-05-02T00:00:00Z",
        updated_at="2026-05-02T00:00:00Z",
        expired_at=expired,
    )


class TestChatSessionService:
    def test_create_session_returns_row_after_re_fetch(self) -> None:
        session_repo = _StubSessionRepo()
        service = ChatSessionService(session_repo, _StubMessageRepo())
        row = service.create_session(project_id=7, title="hello")
        assert row.project_id == 7
        assert row.title == "hello"
        assert session_repo.create_calls == [{"project_id": 7, "title": "hello"}]

    def test_create_session_raises_when_re_fetch_returns_none(self) -> None:
        session_repo = _StubSessionRepo()
        session_repo.suppress_re_fetch = True
        service = ChatSessionService(session_repo, _StubMessageRepo())
        with pytest.raises(ChatSessionNotFound):
            service.create_session(project_id=1, title="t")

    def test_list_sessions_passes_pagination_through(self) -> None:
        rows = [_row(2, 5), _row(1, 5)]
        session_repo = _StubSessionRepo()
        session_repo.list_return = (rows, 2)
        service = ChatSessionService(session_repo, _StubMessageRepo())
        items, total = service.list_sessions(5, offset=10, limit=25)
        assert items == rows
        assert total == 2
        assert session_repo.list_calls == [
            {
                "project_id": 5,
                "offset": 10,
                "limit": 25,
                "include_expired": True,
            }
        ]

    def test_get_session_or_raise_returns_matching_session(self) -> None:
        session_repo = _StubSessionRepo({1: _row(1, 5)})
        service = ChatSessionService(session_repo, _StubMessageRepo())
        assert service.get_session_or_raise(1, 5).id == 1

    def test_get_session_or_raise_raises_on_missing_session(self) -> None:
        service = ChatSessionService(_StubSessionRepo(), _StubMessageRepo())
        with pytest.raises(ChatSessionNotFound):
            service.get_session_or_raise(1, 5)

    def test_get_session_or_raise_raises_on_wrong_project(self) -> None:
        session_repo = _StubSessionRepo({1: _row(1, 99)})
        service = ChatSessionService(session_repo, _StubMessageRepo())
        with pytest.raises(ChatSessionNotFound):
            service.get_session_or_raise(1, 5)

    def test_delete_session_calls_delete_after_validation(self) -> None:
        session_repo = _StubSessionRepo({1: _row(1, 5)})
        service = ChatSessionService(session_repo, _StubMessageRepo())
        service.delete_session(1, 5)
        assert session_repo.delete_calls == [1]

    def test_delete_session_raises_when_session_belongs_to_other_project(
        self,
    ) -> None:
        session_repo = _StubSessionRepo({1: _row(1, 99)})
        service = ChatSessionService(session_repo, _StubMessageRepo())
        with pytest.raises(ChatSessionNotFound):
            service.delete_session(1, 5)
        assert session_repo.delete_calls == []

    def test_list_messages_passes_pagination_through(self) -> None:
        message_repo = _StubMessageRepo()
        message_repo.list_return = ([], 0)
        service = ChatSessionService(_StubSessionRepo(), message_repo)
        service.list_messages(42, offset=5, limit=20)
        assert message_repo.list_calls == [{"session_id": 42, "offset": 5, "limit": 20}]

    def test_append_user_message_uses_user_role(self) -> None:
        message_repo = _StubMessageRepo()
        service = ChatSessionService(_StubSessionRepo(), message_repo)
        message_id = service.append_user_message(42, "hi there")
        assert message_id == 99
        assert message_repo.append_calls == [
            {
                "session_id": 42,
                "role": "user",
                "content": "hi there",
                "model": None,
            }
        ]

    def test_session_summary_metrics_returns_last_created_and_count(self) -> None:
        message_repo = _StubMessageRepo()
        message_repo.last_at = "2026-05-02T01:00:00Z"
        message_repo.count = 4
        service = ChatSessionService(_StubSessionRepo(), message_repo)
        last_at, count = service.session_summary_metrics(42)
        assert last_at == "2026-05-02T01:00:00Z"
        assert count == 4

    def test_for_project_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            ChatSessionService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_for_project_raises_when_project_archived(self) -> None:
        archived = ProjectRow(
            id=7,
            name="p",
            path="/tmp/p",
            created_at="2026-05-01T00:00:00Z",
            archived_at="2026-05-01T00:00:00Z",
        )
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: archived)
        with pytest.raises(ProjectNotFound):
            ChatSessionService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_session_repo_and_message_repo_properties_expose_handles(self) -> None:
        session_repo = _StubSessionRepo()
        message_repo = _StubMessageRepo()
        service = ChatSessionService(session_repo, message_repo)
        assert service.session_repo is session_repo
        assert service.message_repo is message_repo


# Streaming orchestration


class _StubChatSink:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def emit(self, event: Any) -> None:
        self.events.append(event)


class _FakeProvider:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks
        self.model = "fake-chat-model"

    def is_available(self) -> bool:
        return True

    def complete(self, prompt: str, **kwargs: Any) -> str:  # noqa: ARG002
        return ""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:  # noqa: ARG002
        return ""

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        del messages, kwargs
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c


class _StubQueryEngine:
    def search(
        self,
        raw_input: str = "",
        n_results: int = 20,
        query: Any = None,
    ) -> list[dict[str, Any]]:
        del raw_input, n_results, query
        return []


def _composer_for(provider: _FakeProvider) -> SimpleNamespace:
    return SimpleNamespace(
        query_engine=_StubQueryEngine(),
        provider=provider,
        model_name=provider.model,
    )


def _make_session_service_with_session(
    session_id: int = 1,
    project_id: int = 5,
    *,
    expired: str | None = None,
) -> tuple[ChatSessionService, _StubSessionRepo, _StubMessageRepo]:
    session_repo = _StubSessionRepo(
        {session_id: _row(session_id, project_id, expired=expired)}
    )
    message_repo = _StubMessageRepo()
    return ChatSessionService(session_repo, message_repo), session_repo, message_repo


@pytest.fixture(autouse=True)
def _reset_chat_run_registry():
    get_chat_run_registry().reset()
    yield
    get_chat_run_registry().reset()


class TestChatSessionServiceSendMessage:
    @pytest.mark.asyncio
    async def test_returns_handle_and_persists_user_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, _session_repo, message_repo = _make_session_service_with_session(
            session_id=1, project_id=5
        )
        provider = _FakeProvider(["a"])
        monkeypatch.setattr(
            "application.chat.session_service.ChatStreamComposer.for_project",
            lambda *_args, **_kwargs: _composer_for(provider),
        )
        result = await service.send_message(
            project_id=5,
            session_id=1,
            content="hi",
            chat_sink=_StubChatSink(),
            project_registry=SimpleNamespace(),  # type: ignore[arg-type]
            knowledge_base_cache={},
            base_path="/tmp",
        )
        await asyncio.sleep(0)  # let driver start
        assert isinstance(result, SendMessageHandle)
        assert result.user_message_id == 99
        assert result.session_id == 1
        assert result.project_id == 5
        assert {c["role"] for c in message_repo.append_calls} >= {"user"}
        # Allow the driver task to finish.
        for _ in range(50):
            if get_chat_run_registry().get(1) is None:
                break
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_raises_session_not_found_for_unknown_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        monkeypatch.setattr(
            "application.chat.session_service.ChatStreamComposer.for_project",
            lambda *_args, **_kwargs: _composer_for(_FakeProvider([])),
        )
        with pytest.raises(ChatSessionNotFound):
            await service.send_message(
                project_id=5,
                session_id=99,
                content="hi",
                chat_sink=_StubChatSink(),
                project_registry=SimpleNamespace(),  # type: ignore[arg-type]
                knowledge_base_cache={},
                base_path="/tmp",
            )

    @pytest.mark.asyncio
    async def test_raises_session_expired_for_sealed_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, *_ = _make_session_service_with_session(
            session_id=1, project_id=5, expired="2026-05-02T01:00:00Z"
        )
        monkeypatch.setattr(
            "application.chat.session_service.ChatStreamComposer.for_project",
            lambda *_args, **_kwargs: _composer_for(_FakeProvider([])),
        )
        with pytest.raises(ChatSessionExpired):
            await service.send_message(
                project_id=5,
                session_id=1,
                content="hi",
                chat_sink=_StubChatSink(),
                project_registry=SimpleNamespace(),  # type: ignore[arg-type]
                knowledge_base_cache={},
                base_path="/tmp",
            )

    @pytest.mark.asyncio
    async def test_raises_already_running_when_registry_has_handle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        get_chat_run_registry().register(
            session_id=1,
            project_id=5,
            user_message_id=42,
            task=MagicMock(spec=asyncio.Task),
        )
        monkeypatch.setattr(
            "application.chat.session_service.ChatStreamComposer.for_project",
            lambda *_args, **_kwargs: _composer_for(_FakeProvider([])),
        )
        with pytest.raises(ChatStreamAlreadyRunning):
            await service.send_message(
                project_id=5,
                session_id=1,
                content="hi",
                chat_sink=_StubChatSink(),
                project_registry=SimpleNamespace(),  # type: ignore[arg-type]
                knowledge_base_cache={},
                base_path="/tmp",
            )


class TestChatSessionServiceCancelStream:
    def test_cancels_in_flight_task(self) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        task = MagicMock(spec=asyncio.Task)
        get_chat_run_registry().register(
            session_id=1,
            project_id=5,
            user_message_id=42,
            task=task,
        )
        service.cancel_stream(1, 5)
        task.cancel.assert_called_once_with()

    def test_raises_session_not_found_for_unknown(self) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        with pytest.raises(ChatSessionNotFound):
            service.cancel_stream(99, 5)

    def test_raises_stream_not_running_when_registry_empty(self) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        with pytest.raises(ChatStreamNotRunning):
            service.cancel_stream(1, 5)


class TestChatSessionServicePeekActiveStream:
    def test_returns_handle_when_registered(self) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        task = MagicMock(spec=asyncio.Task)
        get_chat_run_registry().register(
            session_id=1,
            project_id=5,
            user_message_id=42,
            task=task,
        )
        handle = service.peek_active_stream(1)
        assert handle is not None
        assert handle.user_message_id == 42

    def test_returns_none_when_not_registered(self) -> None:
        service, *_ = _make_session_service_with_session(session_id=1, project_id=5)
        assert service.peek_active_stream(1) is None
