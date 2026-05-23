"""Integration tests for RepositoryRepository."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas.repo_service import RepoService  # noqa: E402
from core.config.schemas.repository import RepoAuth, Repository  # noqa: E402
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


RepoFactory = Callable[..., Repository]


@pytest.fixture()
def make_repo(tmp_path: Path) -> RepoFactory:
    """Build Repository objects backed by a real on-disk path (tmp_path)."""

    def _make(name: str, **overrides: object) -> Repository:
        service_kwargs: dict[str, object] = {
            "name": "default",
            "relative_path": "",
            "type": ["api"],
            "languages": ["python"],
        }
        repo_kwargs: dict[str, object] = {
            "name": name,
            "path": str(tmp_path),
        }
        _service_fields = {
            "type",
            "languages",
            "docker_path",
            "container_name",
            "base_urls",
            "test_dirs",
            "ignore_dirs",
            "dependencies_file",
            "crawl_enabled",
            "relative_path",
        }
        for key in list(overrides.keys()):
            if key in _service_fields:
                service_kwargs[key] = overrides.pop(key)
        repo_kwargs.update(overrides)
        service = RepoService(
            name=str(service_kwargs["name"]),
            relative_path=str(service_kwargs.get("relative_path", "")),
            type=service_kwargs.get("type", []),  # type: ignore[arg-type]
            languages=service_kwargs.get("languages", []),  # type: ignore[arg-type]
            docker_path=str(service_kwargs.get("docker_path", "")),
            container_name=str(service_kwargs.get("container_name", "")),
            base_urls=service_kwargs.get("base_urls", []),  # type: ignore[arg-type]
            test_dirs=service_kwargs.get("test_dirs", []),  # type: ignore[arg-type]
            ignore_dirs=service_kwargs.get("ignore_dirs", []),  # type: ignore[arg-type]
            dependencies_file=str(service_kwargs.get("dependencies_file", "")),
            crawl_enabled=bool(service_kwargs.get("crawl_enabled", True)),
        )
        repo_kwargs["services"] = [service]
        return Repository(**repo_kwargs)  # type: ignore[arg-type]

    return _make


class TestInsertAndLookups:
    def test_insert_returns_id_and_round_trip(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("alpha"))
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.id == rid
        assert row.name == "alpha"
        assert not repos.is_deleted(rid)

    def test_round_trip_preserves_collection_and_auth_columns(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        repo = make_repo(
            "with-collections",
            type=["api", "ui"],
            languages=["python", "typescript"],
            base_urls=["http://localhost:3000"],
            test_dirs=["tests/", "spec/"],
            ignore_dirs=["dist/"],
            xsstrike_headers={"X-Auth": "abc"},
            dalfox_headers={"X-Foo": "bar"},
            katana_headers={"X-K": "1"},
            auth=RepoAuth(login_url="http://localhost/login", username="u"),
        )
        rid = repos.insert(repo)
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.services[0].type == ["api", "ui"]
        assert row.services[0].languages == ["python", "typescript"]
        assert row.services[0].base_urls == ["http://localhost:3000"]
        assert row.services[0].test_dirs == ["tests/", "spec/"]
        assert row.services[0].ignore_dirs == ["dist/"]
        assert row.xsstrike_headers == {"X-Auth": "abc"}
        assert row.dalfox_headers == {"X-Foo": "bar"}
        assert row.katana_headers == {"X-K": "1"}
        assert row.auth is not None
        assert row.auth.login_url == "http://localhost/login"
        assert row.auth.username == "u"

    def test_get_by_name(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        repos.insert(make_repo("charlie"))
        row = repos.get_by_name("charlie")
        assert row is not None
        assert row.name == "charlie"

    def test_get_by_name_excludes_soft_deleted(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("delta"))
        repos.soft_delete(rid)
        assert repos.get_by_name("delta") is None

    def test_find_id_by_name(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("echo"))
        assert repos.find_id_by_name("echo") == rid
        assert repos.find_id_by_name("nope") is None

    def test_unknown_id_returns_none(self, repos: RepositoryRepository) -> None:
        assert repos.get_by_id(999) is None


class TestListing:
    def test_list_active_filters_deleted_and_orders_by_name(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        repos.insert(make_repo("zulu"))
        rid_alpha = repos.insert(make_repo("alpha"))
        rid_mike = repos.insert(make_repo("mike"))
        repos.soft_delete(rid_alpha)

        names = [r.name for r in repos.list_active()]
        assert names == ["mike", "zulu"]
        assert rid_alpha not in {r.id for r in repos.list_active()}
        assert rid_mike in {r.id for r in repos.list_active()}

    def test_list_all_includes_deleted(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("alpha"))
        repos.soft_delete(rid)
        assert any(r.id == rid for r in repos.list_all())


class TestRenameAndSoftDelete:
    def test_rename(self, repos: RepositoryRepository, make_repo: RepoFactory) -> None:
        rid = repos.insert(make_repo("old-name"))
        repos.rename(rid, "new-name")
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.name == "new-name"

    def test_soft_delete_sets_timestamp(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("goldfish"))
        repos.soft_delete(rid)
        assert repos.is_deleted(rid)

    def test_soft_delete_idempotent(
        self,
        repos: RepositoryRepository,
        make_repo: RepoFactory,
        factory: ConnectionFactory,
    ) -> None:
        rid = repos.insert(make_repo("goldfish"))
        repos.soft_delete(rid, when="2026-04-26T10:00:00+00:00")
        repos.soft_delete(rid, when="2026-04-26T11:00:00+00:00")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT deleted_at FROM repositories WHERE id = ?",
                (rid,),
            ).fetchone()
        # The second soft_delete call must not overwrite the original timestamp.
        assert row["deleted_at"] == "2026-04-26T10:00:00+00:00"

    def test_restore_clears_deleted_at(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("phoenix"))
        repos.soft_delete(rid)
        repos.restore(rid)
        assert not repos.is_deleted(rid)


class TestUrlSeedFile:
    def test_set_and_clear_url_seed_file(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("seedy"))
        repos.set_url_seed_file(rid, "/tmp/endpoints/seedy-1700000000/spec.json")
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.url_seed_file == "/tmp/endpoints/seedy-1700000000/spec.json"
        repos.set_url_seed_file(rid, None)
        row2 = repos.get_by_id(rid)
        assert row2 is not None
        assert row2.url_seed_file is None


class TestUpdate:
    def test_update_replaces_columns(
        self, repos: RepositoryRepository, make_repo: RepoFactory
    ) -> None:
        rid = repos.insert(make_repo("project-a"))
        existing = repos.get_by_id(rid)
        assert existing is not None
        updated_service = existing.services[0].model_copy(update={"languages": ["go"]})
        merged = existing.model_copy(update={"services": [updated_service]})
        repos.update(rid, merged)
        row = repos.get_by_id(rid)
        assert row is not None
        assert row.services[0].languages == ["go"]


class TestSchemaSanity:
    def test_findings_repo_id_column_added(self, factory: ConnectionFactory) -> None:
        with factory.connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(findings)")}
        assert "repo_id" in cols

    def test_repositories_columns(self, factory: ConnectionFactory) -> None:
        with factory.connect() as conn:
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(repositories)").fetchall()
            }
        for required in (
            "id",
            "name",
            "path",
            "services_json",
            "auth_json",
            "url_seed_file",
            "created_at",
            "deleted_at",
        ):
            assert required in cols

    def test_init_schema_idempotent(self, tmp_path: Path) -> None:
        f = ConnectionFactory(tmp_path / "findings.db")
        f.init_schema()
        f.init_schema()
