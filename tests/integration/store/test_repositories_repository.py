"""Integration tests for the Phase 9 RepositoryRepository."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    RepositoryRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repos(factory: ConnectionFactory) -> RepositoryRepository:
    return RepositoryRepository(factory)


class TestInsertAndLookups:
    def test_insert_returns_id_and_round_trip(
        self, repos: RepositoryRepository
    ) -> None:
        u = str(uuid4())
        rid = repos.insert(uuid=u, name="alpha")
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.id == rid
        assert row.uuid == u
        assert row.name == "alpha"
        assert row.deleted_at is None
        assert row.created_at  # set by DEFAULT clause

    def test_get_by_uuid(self, repos: RepositoryRepository) -> None:
        u = str(uuid4())
        rid = repos.insert(uuid=u, name="bravo")
        row = repos.get_by_uuid(u)
        assert row is not None
        assert row.id == rid

    def test_get_by_name(self, repos: RepositoryRepository) -> None:
        repos.insert(uuid=str(uuid4()), name="charlie")
        row = repos.get_by_name("charlie")
        assert row is not None
        assert row.name == "charlie"

    def test_get_by_name_excludes_soft_deleted(
        self, repos: RepositoryRepository
    ) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="delta")
        repos.soft_delete(rid)
        assert repos.get_by_name("delta") is None

    def test_find_id_by_name(self, repos: RepositoryRepository) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="echo")
        assert repos.find_id_by_name("echo") == rid
        assert repos.find_id_by_name("nope") is None

    def test_unknown_id_returns_none(self, repos: RepositoryRepository) -> None:
        assert repos.get_by_id(999) is None
        assert repos.get_by_uuid("missing") is None


class TestUniqueUuid:
    def test_duplicate_uuid_raises(self, repos: RepositoryRepository) -> None:
        u = str(uuid4())
        repos.insert(uuid=u, name="first")
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            repos.insert(uuid=u, name="second")

    def test_duplicate_name_allowed(self, repos: RepositoryRepository) -> None:
        repos.insert(uuid=str(uuid4()), name="dupe")
        repos.insert(uuid=str(uuid4()), name="dupe")
        assert len(repos.list_active()) == 2


class TestListing:
    def test_list_active_filters_deleted_and_orders_by_name(
        self, repos: RepositoryRepository
    ) -> None:
        repos.insert(uuid=str(uuid4()), name="zulu")
        rid_alpha = repos.insert(uuid=str(uuid4()), name="alpha")
        rid_mike = repos.insert(uuid=str(uuid4()), name="mike")
        repos.soft_delete(rid_alpha)

        names = [r.name for r in repos.list_active()]
        assert names == ["mike", "zulu"]
        assert rid_alpha not in {r.id for r in repos.list_active()}
        assert rid_mike in {r.id for r in repos.list_active()}

    def test_list_all_includes_deleted(self, repos: RepositoryRepository) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="alpha")
        repos.soft_delete(rid)
        assert any(r.id == rid for r in repos.list_all())


class TestRenameAndSoftDelete:
    def test_rename(self, repos: RepositoryRepository) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="old-name")
        repos.rename(rid, "new-name")
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.name == "new-name"

    def test_soft_delete_sets_timestamp(self, repos: RepositoryRepository) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="goldfish")
        repos.soft_delete(rid)
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.deleted_at is not None

    def test_soft_delete_idempotent(self, repos: RepositoryRepository) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="goldfish")
        repos.soft_delete(rid, when="2026-04-26T10:00:00+00:00")
        first = repos.get_by_id(rid)
        repos.soft_delete(rid, when="2026-04-26T11:00:00+00:00")
        second = repos.get_by_id(rid)
        assert first is not None and second is not None
        # The second call must not overwrite the original deleted_at.
        assert first.deleted_at == second.deleted_at

    def test_restore_clears_deleted_at(self, repos: RepositoryRepository) -> None:
        rid = repos.insert(uuid=str(uuid4()), name="phoenix")
        repos.soft_delete(rid)
        repos.restore(rid)
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.deleted_at is None


class TestSchemaMigration:
    def test_findings_repo_id_column_added(self, factory: ConnectionFactory) -> None:
        with factory.connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(findings)")}
        assert "repo_id" in cols

    def test_repositories_table_indexes(self, factory: ConnectionFactory) -> None:
        with factory.connect() as conn:
            indexes = {
                r["name"]
                for r in conn.execute("PRAGMA index_list(repositories)").fetchall()
            }
        assert "idx_repositories_uuid" in indexes
        assert "idx_repositories_deleted" in indexes

    def test_init_schema_idempotent(self, tmp_path: Path) -> None:
        f = ConnectionFactory(tmp_path / "findings.db")
        f.init_schema()
        # Second call must not raise.
        f.init_schema()
