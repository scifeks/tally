"""Integration tests for chat session sealing and retention sweep.

Exercises ``application/chat/sealing.py`` directly against real SQLite
repositories, decoupled from the scan orchestrator.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.chat.sealing import (  # noqa: E402
    purge_chat_for_project,
    seal_sessions_for_project,
)
from core.project_paths import ProjectPaths  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.chat_messages import (  # noqa: E402
    ChatMessageRepository,
)
from infrastructure.store.repositories.chat_sessions import (  # noqa: E402
    ChatSessionRepository,
)

pytestmark = pytest.mark.integration


def _setup(tmp_path: Path) -> tuple[ProjectPaths, ConnectionFactory]:
    paths = ProjectPaths.from_canonical(str(tmp_path), "testproject")
    paths.findings_db.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return paths, factory


def _seed_active(factory: ConnectionFactory, project_id: int, n: int) -> list[int]:
    repo = ChatSessionRepository(factory)
    return [repo.create(project_id=project_id, title=f"active-{i}") for i in range(n)]


def _seed_expired(
    factory: ConnectionFactory,
    project_id: int,
    n: int,
    *,
    base_offset_seconds: int = 0,
) -> list[int]:
    """Create *n* expired sessions with strictly increasing expired_at."""
    repo = ChatSessionRepository(factory)
    ids: list[int] = []
    base = datetime.now(UTC) - timedelta(days=10)
    for i in range(n):
        sid = repo.create(project_id=project_id, title=f"expired-{i}")
        when = (base + timedelta(seconds=base_offset_seconds + i)).isoformat()
        repo.mark_expired([sid], when=when)
        ids.append(sid)
    return ids


def test_seal_marks_all_active_sessions_expired(tmp_path: Path) -> None:
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    project_id = 1
    active = _seed_active(factory, project_id=project_id, n=5)

    seal_sessions_for_project(
        project_id,
        session_repo=ChatSessionRepository(factory),
        retention_count=100,
    )

    for sid in active:
        row = repo.get(sid)
        assert row is not None
        assert row.expired_at is not None


def test_seal_skips_already_expired_rows(tmp_path: Path) -> None:
    """Already-expired rows preserve their original expired_at timestamp."""
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    project_id = 1
    expired_ids = _seed_expired(factory, project_id=project_id, n=3)
    original_timestamps = {sid: repo.get(sid).expired_at for sid in expired_ids}  # type: ignore[union-attr]

    seal_sessions_for_project(
        project_id,
        session_repo=ChatSessionRepository(factory),
        retention_count=100,
    )

    for sid in expired_ids:
        row = repo.get(sid)
        assert row is not None
        assert row.expired_at == original_timestamps[sid]


def test_seal_with_retention_sweep_drops_oldest_expired(tmp_path: Path) -> None:
    """With retention_count=K, only the K most-recent expired sessions survive."""
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    msgs = ChatMessageRepository(factory)
    project_id = 1

    # Seed 5 expired sessions; oldest first by id.
    expired_ids = _seed_expired(factory, project_id=project_id, n=5)
    # Add a message to the oldest so we can prove cascade-delete worked.
    msgs.append(session_id=expired_ids[0], role="user", content="oldest user")

    seal_sessions_for_project(
        project_id,
        session_repo=ChatSessionRepository(factory),
        retention_count=2,
    )

    # Oldest 3 deleted (5 - keep=2 = 3); newest 2 survive.
    surviving = repo.list_for_project(project_id)
    surviving_ids = sorted(r.id for r in surviving)
    assert surviving_ids == sorted(expired_ids[-2:])
    # Cascade removed messages for the deleted oldest session.
    assert msgs.count_for_session(expired_ids[0]) == 0


def test_seal_retention_zero_keeps_every_expired_session(tmp_path: Path) -> None:
    """retention_count=0 disables the sweep; every expired session survives."""
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    project_id = 1
    expired_ids = _seed_expired(factory, project_id=project_id, n=4)

    seal_sessions_for_project(
        project_id,
        session_repo=ChatSessionRepository(factory),
        retention_count=0,
    )

    surviving_ids = sorted(r.id for r in repo.list_for_project(project_id))
    assert surviving_ids == sorted(expired_ids)


def test_seal_followed_by_tight_sweep_keeps_only_retention_count(
    tmp_path: Path,
) -> None:
    """Sealing converts active→expired, then sweep prunes to retention_count."""
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    project_id = 1
    active_ids = _seed_active(factory, project_id=project_id, n=3)

    seal_sessions_for_project(
        project_id,
        session_repo=ChatSessionRepository(factory),
        retention_count=1,
    )

    surviving = repo.list_for_project(project_id, include_expired=True)
    surviving_ids = sorted(r.id for r in surviving)
    # Only the newest stays (retention_count=1).
    assert surviving_ids == [active_ids[-1]]
    assert surviving[0].expired_at is not None


def test_seal_negative_retention_raises(tmp_path: Path) -> None:
    _, factory = _setup(tmp_path)
    with pytest.raises(ValueError):
        seal_sessions_for_project(
            1,
            session_repo=ChatSessionRepository(factory),
            retention_count=-1,
        )


def test_purge_hard_deletes_all_sessions_and_messages(tmp_path: Path) -> None:
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    msgs = ChatMessageRepository(factory)
    project_id = 1

    active_ids = _seed_active(factory, project_id=project_id, n=2)
    expired_ids = _seed_expired(factory, project_id=project_id, n=2)
    for sid in active_ids + expired_ids:
        msgs.append(session_id=sid, role="user", content=f"hi-{sid}")

    deleted = purge_chat_for_project(
        project_id, session_repo=ChatSessionRepository(factory)
    )
    assert deleted == 4

    assert repo.list_for_project(project_id, include_expired=True) == []
    for sid in active_ids + expired_ids:
        assert msgs.count_for_session(sid) == 0


def test_purge_leaves_other_projects_untouched(tmp_path: Path) -> None:
    _, factory = _setup(tmp_path)
    repo = ChatSessionRepository(factory)
    keep_project = 1
    purge_project = 2

    keep_ids = _seed_active(factory, project_id=keep_project, n=3)
    _seed_active(factory, project_id=purge_project, n=2)

    purge_chat_for_project(purge_project, session_repo=ChatSessionRepository(factory))

    surviving = repo.list_for_project(keep_project, include_expired=True)
    assert sorted(r.id for r in surviving) == sorted(keep_ids)
    assert repo.list_for_project(purge_project, include_expired=True) == []
