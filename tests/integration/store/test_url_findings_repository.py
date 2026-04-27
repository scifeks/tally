"""Integration tests for UrlFindingRepository (Phase 9 Step 3)."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    RepositoryRepository,
)
from infrastructure.store.repositories.url_findings import (  # noqa: E402
    UrlFindingRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo_id(factory: ConnectionFactory) -> int:
    rr = RepositoryRepository(factory)
    return rr.insert(uuid=str(uuid4()), name="alpha")


@pytest.fixture()
def run_id(factory: ConnectionFactory) -> int:
    """Seed a scan_runs row so SCAN-source url_findings can FK against it."""
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO scan_runs (args, created_at) VALUES (?, ?)",
            ("{}", "2026-04-26T00:00:00"),
        )
        return cur.lastrowid  # type: ignore[return-value]


@pytest.fixture()
def url_repo(factory: ConnectionFactory) -> UrlFindingRepository:
    return UrlFindingRepository(factory)


def _scan(
    repo_id: int,
    *,
    method: str = "GET",
    host: str = "api.example.com",
    port: int = 443,
    path: str = "/api/users",
    tool: UrlTool = UrlTool.KATANA,
    run_id: int | None = None,
    meta: dict | None = None,
) -> UrlFinding:
    return UrlFinding(
        repo_id=repo_id,
        source=UrlSource.SCAN,
        tool=tool,
        run_id=run_id,
        method=method,
        protocol="https",
        host=host,
        port=port,
        path=path,
        file_path=None,
        meta=meta or {},
    )


def _user(
    repo_id: int,
    *,
    file_path: str,
    method: str = "GET",
    path: str = "/api/u",
    meta: dict | None = None,
) -> UrlFinding:
    return UrlFinding(
        repo_id=repo_id,
        source=UrlSource.USER,
        tool=None,
        run_id=None,
        method=method,
        protocol="https",
        host="api.example.com",
        port=443,
        path=path,
        file_path=file_path,
        meta=meta or {},
    )


class TestInsert:
    def test_inserts_rows_and_returns_count(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        n = url_repo.insert_many(
            [
                _scan(repo_id, path="/a"),
                _scan(repo_id, path="/b"),
            ]
        )
        assert n == 2
        rows = url_repo.list_for_repo(repo_id)
        paths = sorted(r.path for r in rows)
        assert paths == ["/a", "/b"]

    def test_dedup_within_single_batch(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        n = url_repo.insert_many(
            [
                _scan(repo_id, path="/dup"),
                _scan(repo_id, path="/dup"),
                _scan(repo_id, path="/different"),
            ]
        )
        # The unique index silently absorbs the dup; rowcount reflects
        # actual inserts only.
        assert n == 2

    def test_same_url_different_tools_both_kept(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many([_scan(repo_id, path="/api/x", tool=UrlTool.KATANA)])
        url_repo.insert_many([_scan(repo_id, path="/api/x", tool=UrlTool.NOIR)])
        rows = url_repo.list_for_repo(repo_id)
        assert len(rows) == 2
        assert {r.tool for r in rows} == {UrlTool.KATANA, UrlTool.NOIR}

    def test_user_file_distinguishes_uploads(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many(
            [_user(repo_id, file_path="/uploads/a.json", path="/api/x")]
        )
        url_repo.insert_many(
            [_user(repo_id, file_path="/uploads/b.json", path="/api/x")]
        )
        # Same URL from two different uploads → two rows (file_path is in
        # the unique index).
        rows = url_repo.list_for_repo(repo_id)
        assert len(rows) == 2

    def test_meta_round_trip(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        original = {"original_file": {"summary": "orig", "responses": {"200": {}}}}
        url_repo.insert_many([_scan(repo_id, path="/a", meta=original)])
        rows = url_repo.list_for_repo(repo_id)
        assert rows[0].meta == original


class TestDelete:
    def test_delete_for_repo_and_tool_only_wipes_that_pair(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many(
            [
                _scan(repo_id, path="/k1", tool=UrlTool.KATANA),
                _scan(repo_id, path="/k2", tool=UrlTool.KATANA),
                _scan(repo_id, path="/n1", tool=UrlTool.NOIR),
            ]
        )
        n = url_repo.delete_for_repo_and_tool(repo_id, UrlTool.KATANA)
        assert n == 2
        rows = url_repo.list_for_repo(repo_id)
        assert {r.path for r in rows} == {"/n1"}

    def test_delete_for_user_file(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many(
            [
                _user(repo_id, file_path="/uploads/a.json", path="/x"),
                _user(repo_id, file_path="/uploads/a.json", path="/y"),
                _user(repo_id, file_path="/uploads/b.json", path="/z"),
            ]
        )
        n = url_repo.delete_for_user_file(repo_id, "/uploads/a.json")
        assert n == 2
        rows = url_repo.list_for_repo(repo_id)
        assert {r.path for r in rows} == {"/z"}

    def test_delete_for_repo(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many([_scan(repo_id, path="/a"), _scan(repo_id, path="/b")])
        n = url_repo.delete_for_repo(repo_id)
        assert n == 2
        assert url_repo.list_for_repo(repo_id) == []


class TestPagination:
    def test_pagination_filters_and_total(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many([_scan(repo_id, path=f"/api/{i}") for i in range(15)])
        rows, total = url_repo.list_paginated(repo_id=repo_id, offset=0, limit=10)
        assert total == 15
        assert len(rows) == 10
        page2, _ = url_repo.list_paginated(repo_id=repo_id, offset=10, limit=10)
        assert len(page2) == 5

    def test_filter_by_source(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many([_scan(repo_id, path="/scan")])
        url_repo.insert_many(
            [_user(repo_id, file_path="/uploads/x.json", path="/user")]
        )
        scan_only, _ = url_repo.list_paginated(repo_id=repo_id, source=UrlSource.SCAN)
        assert {r.path for r in scan_only} == {"/scan"}

    def test_search_path_substring(
        self, url_repo: UrlFindingRepository, repo_id: int
    ) -> None:
        url_repo.insert_many(
            [
                _scan(repo_id, path="/api/users"),
                _scan(repo_id, path="/api/orders"),
                _scan(repo_id, path="/admin"),
            ]
        )
        rows, total = url_repo.list_paginated(repo_id=repo_id, search="/api/")
        assert total == 2
        assert {r.path for r in rows} == {"/api/users", "/api/orders"}

    def test_excludes_soft_deleted_repos(
        self, factory: ConnectionFactory, url_repo: UrlFindingRepository
    ) -> None:
        rr = RepositoryRepository(factory)
        active_id = rr.insert(uuid=str(uuid4()), name="active")
        deleted_id = rr.insert(uuid=str(uuid4()), name="deleted")
        url_repo.insert_many([_scan(active_id, path="/a")])
        url_repo.insert_many([_scan(deleted_id, path="/d")])
        rr.soft_delete(deleted_id)

        rows, total = url_repo.list_paginated(offset=0, limit=100)
        assert total == 1
        assert {r.path for r in rows} == {"/a"}


class TestForeignKeys:
    def test_repo_cascade_delete_removes_url_rows(
        self, factory: ConnectionFactory, url_repo: UrlFindingRepository
    ) -> None:
        # ON DELETE CASCADE only fires on hard delete, not soft delete.
        # Hard delete the repositories row directly to verify the FK.
        rr = RepositoryRepository(factory)
        rid = rr.insert(uuid=str(uuid4()), name="dynamite")
        url_repo.insert_many([_scan(rid, path="/x"), _scan(rid, path="/y")])
        with factory.connect() as conn:
            conn.execute("DELETE FROM repositories WHERE id = ?", (rid,))
        assert url_repo.list_for_repo(rid) == []


class TestDomainGuards:
    def test_scan_requires_tool(self, repo_id: int) -> None:
        with pytest.raises(ValueError):
            UrlFinding(
                repo_id=repo_id,
                source=UrlSource.SCAN,
                tool=None,
                run_id=1,
                method="GET",
                protocol="https",
                host="x",
                port=443,
                path="/",
            )

    def test_user_must_have_no_tool(self, repo_id: int) -> None:
        with pytest.raises(ValueError):
            UrlFinding(
                repo_id=repo_id,
                source=UrlSource.USER,
                tool=UrlTool.KATANA,
                run_id=None,
                method="GET",
                protocol="https",
                host="x",
                port=443,
                path="/",
            )
