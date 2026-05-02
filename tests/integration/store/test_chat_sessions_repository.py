"""Integration tests for ChatSessionRepository."""

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


class TestCreateAndGet:
    def test_create_returns_id_and_round_trip(
        self, sessions: ChatSessionRepository
    ) -> None:
        sid = sessions.create(project_id=42, title="2026-04-25 14:30")
        row = sessions.get(sid)
        assert row is not None
        assert row.id == sid
        assert row.project_id == 42
        assert row.title == "2026-04-25 14:30"
        assert row.expired_at is None
        assert row.created_at == row.updated_at

    def test_get_unknown_returns_none(self, sessions: ChatSessionRepository) -> None:
        assert sessions.get(999) is None


class TestListForProject:
    def test_filters_by_project_and_orders_newest_first(
        self, sessions: ChatSessionRepository
    ) -> None:
        a = sessions.create(project_id=1, title="t1")
        b = sessions.create(project_id=1, title="t2")
        sessions.create(project_id=2, title="other")

        rows = sessions.list_for_project(1)
        assert [r.id for r in rows] == [b, a]

    def test_include_expired_false_omits_expired(
        self, sessions: ChatSessionRepository
    ) -> None:
        active = sessions.create(project_id=1, title="active")
        expired = sessions.create(project_id=1, title="expired")
        sessions.mark_expired([expired])

        all_rows = sessions.list_for_project(1, include_expired=True)
        active_only = sessions.list_for_project(1, include_expired=False)
        assert {r.id for r in all_rows} == {active, expired}
        assert [r.id for r in active_only] == [active]

    def test_active_and_expired_helpers(self, sessions: ChatSessionRepository) -> None:
        a = sessions.create(project_id=1, title="a")
        e = sessions.create(project_id=1, title="e")
        sessions.mark_expired([e])

        assert [r.id for r in sessions.list_active_for_project(1)] == [a]
        assert [r.id for r in sessions.list_expired_for_project(1)] == [e]


class TestExpireAndTouch:
    def test_mark_expired_sets_timestamp(self, sessions: ChatSessionRepository) -> None:
        sid = sessions.create(project_id=1, title="t")
        sessions.mark_expired([sid], when="2026-04-25T15:00:00+00:00")
        row = sessions.get(sid)
        assert row is not None
        assert row.expired_at == "2026-04-25T15:00:00+00:00"

    def test_mark_expired_does_not_overwrite_existing_timestamp(
        self, sessions: ChatSessionRepository
    ) -> None:
        sid = sessions.create(project_id=1, title="t")
        sessions.mark_expired([sid], when="2026-04-25T15:00:00+00:00")
        sessions.mark_expired([sid], when="2026-04-25T16:00:00+00:00")
        row = sessions.get(sid)
        assert row is not None
        assert row.expired_at == "2026-04-25T15:00:00+00:00"

    def test_mark_expired_empty_iterable_is_noop(
        self, sessions: ChatSessionRepository
    ) -> None:
        # Must not raise and must not touch any row.
        sessions.mark_expired([])

    def test_touch_updates_timestamp(self, sessions: ChatSessionRepository) -> None:
        sid = sessions.create(project_id=1, title="t")
        sessions.touch(sid, when="2026-04-25T17:00:00+00:00")
        row = sessions.get(sid)
        assert row is not None
        assert row.updated_at == "2026-04-25T17:00:00+00:00"


class TestDeleteCascade:
    def test_delete_removes_session_and_messages(
        self,
        sessions: ChatSessionRepository,
        messages: ChatMessageRepository,
    ) -> None:
        sid = sessions.create(project_id=1, title="t")
        messages.append(session_id=sid, role="user", content="hi")
        messages.append(
            session_id=sid,
            role="assistant",
            content="hello",
            model="claude-opus",
        )
        assert messages.count_for_session(sid) == 2

        sessions.delete(sid)

        assert sessions.get(sid) is None
        assert messages.count_for_session(sid) == 0


class TestRetentionSweep:
    def test_select_for_retention_returns_excess_expired(
        self, sessions: ChatSessionRepository
    ) -> None:
        ids = [sessions.create(project_id=1, title=f"t{i}") for i in range(5)]
        sessions.mark_expired(ids)

        excess = sessions.select_for_retention(1, keep=2)
        # Newest first: keep ids[4], ids[3]; sweep ids[2], ids[1], ids[0].
        assert [r.id for r in excess] == [ids[2], ids[1], ids[0]]

    def test_active_sessions_are_never_swept(
        self, sessions: ChatSessionRepository
    ) -> None:
        for i in range(5):
            sessions.create(project_id=1, title=f"t{i}")
        assert sessions.select_for_retention(1, keep=0) == []

    def test_keep_geq_total_returns_empty(
        self, sessions: ChatSessionRepository
    ) -> None:
        ids = [sessions.create(project_id=1, title=f"t{i}") for i in range(3)]
        sessions.mark_expired(ids)
        assert sessions.select_for_retention(1, keep=10) == []

    def test_negative_keep_raises(self, sessions: ChatSessionRepository) -> None:
        with pytest.raises(ValueError):
            sessions.select_for_retention(1, keep=-1)


class TestSchemaIndexes:
    def test_indexes_are_created(self, factory: ConnectionFactory) -> None:
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type='index' AND tbl_name='chat_sessions'"
            ).fetchall()
        names = {r["name"] for r in rows}
        assert "idx_chat_sessions_project_created" in names
        assert "idx_chat_sessions_project_expired" in names
