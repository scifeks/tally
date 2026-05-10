"""Integration tests for ChatMessageRepository."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.chat_messages import (  # noqa: E402
    ChatMessageRepository,
)
from infrastructure.store.repositories.chat_sessions import (  # noqa: E402
    ChatSessionRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "tally.db")
    f.init_schema()
    return f


@pytest.fixture()
def sessions(factory: ConnectionFactory) -> ChatSessionRepository:
    return ChatSessionRepository(factory)


@pytest.fixture()
def messages(factory: ConnectionFactory) -> ChatMessageRepository:
    return ChatMessageRepository(factory)


@pytest.fixture()
def session_id(sessions: ChatSessionRepository) -> int:
    return sessions.create(project_id=1, title="2026-04-25 14:30")


class TestAppend:
    def test_append_user_turn(
        self, messages: ChatMessageRepository, session_id: int
    ) -> None:
        mid = messages.append(session_id=session_id, role="user", content="hello")
        rows = messages.list_for_session(session_id)
        assert len(rows) == 1
        assert rows[0].id == mid
        assert rows[0].role == "user"
        assert rows[0].content == "hello"
        assert rows[0].model is None

    def test_append_assistant_turn_with_model(
        self, messages: ChatMessageRepository, session_id: int
    ) -> None:
        mid = messages.append(
            session_id=session_id,
            role="assistant",
            content="hi back",
            model="claude-opus",
        )
        row = messages.list_for_session(session_id)[0]
        assert row.id == mid
        assert row.role == "assistant"
        assert row.model == "claude-opus"

    def test_append_rejects_unknown_role(
        self, messages: ChatMessageRepository, session_id: int
    ) -> None:
        with pytest.raises(ValueError):
            messages.append(session_id=session_id, role="system", content="nope")

    def test_append_rejects_user_with_model(
        self, messages: ChatMessageRepository, session_id: int
    ) -> None:
        with pytest.raises(ValueError):
            messages.append(
                session_id=session_id,
                role="user",
                content="hi",
                model="claude-opus",
            )

    def test_check_constraint_rejects_unknown_role(
        self, factory: ConnectionFactory, session_id: int
    ) -> None:
        # The repo guards roles, but the schema also enforces a CHECK
        # so a direct insert fails too.
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            with factory.connect() as conn:
                conn.execute(
                    "INSERT INTO chat_messages"
                    " (session_id, role, content, created_at)"
                    " VALUES (?, 'tool', 'x', '2026-04-25T00:00:00+00:00')",
                    (session_id,),
                )


class TestListForSession:
    def test_returns_messages_in_insertion_order(
        self, messages: ChatMessageRepository, session_id: int
    ) -> None:
        ids = [
            messages.append(session_id=session_id, role="user", content=f"m{i}")
            for i in range(3)
        ]
        rows = messages.list_for_session(session_id)
        assert [r.id for r in rows] == ids

    def test_only_returns_matching_session(
        self,
        messages: ChatMessageRepository,
        sessions: ChatSessionRepository,
        session_id: int,
    ) -> None:
        other = sessions.create(project_id=1, title="other")
        messages.append(session_id=session_id, role="user", content="a")
        messages.append(session_id=other, role="user", content="b")
        assert len(messages.list_for_session(session_id)) == 1
        assert len(messages.list_for_session(other)) == 1


class TestCountAndLast:
    def test_count_and_last_created_at(
        self, messages: ChatMessageRepository, session_id: int
    ) -> None:
        assert messages.count_for_session(session_id) == 0
        assert messages.last_created_at(session_id) is None

        messages.append(session_id=session_id, role="user", content="hi")
        messages.append(
            session_id=session_id,
            role="assistant",
            content="hello",
            model="m",
        )

        assert messages.count_for_session(session_id) == 2
        last = messages.last_created_at(session_id)
        assert last is not None and len(last) > 0


class TestForeignKeyEnforcement:
    def test_orphan_session_id_rejected(self, factory: ConnectionFactory) -> None:
        import sqlite3

        repo = ChatMessageRepository(factory)
        with pytest.raises(sqlite3.IntegrityError):
            repo.append(session_id=999, role="user", content="orphan")


class TestSchemaIndex:
    def test_message_index_exists(self, factory: ConnectionFactory) -> None:
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type='index' AND tbl_name='chat_messages'"
            ).fetchall()
        assert "idx_chat_messages_session" in {r["name"] for r in rows}
