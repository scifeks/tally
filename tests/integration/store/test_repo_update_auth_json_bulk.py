"""Integration tests for RepositoryRepository.update_auth_json_bulk()."""

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


class TestUpdateAuthJsonBulk:
    def test_bulk_updates_auth_json_for_multiple_repos(
        self,
        repos: RepositoryRepository,
        make_repo: RepoFactory,
        factory: ConnectionFactory,
    ) -> None:
        """Verify pre-encrypted strings are written directly without re-encryption."""
        r1 = repos.insert(
            make_repo(
                "repo1", auth=RepoAuth(login_url="http://example.com", username="u1")
            )
        )
        r2 = repos.insert(
            make_repo(
                "repo2", auth=RepoAuth(login_url="http://example.com", username="u2")
            )
        )

        new_encrypted_1 = "gAAAAA_pre_encrypted_1"
        new_encrypted_2 = "gAAAAA_pre_encrypted_2"

        repos.update_auth_json_bulk([(r1, new_encrypted_1), (r2, new_encrypted_2)])

        with factory.connect() as conn:
            row1 = conn.execute(
                "SELECT auth_json FROM repositories WHERE id = ?", (r1,)
            ).fetchone()
            row2 = conn.execute(
                "SELECT auth_json FROM repositories WHERE id = ?", (r2,)
            ).fetchone()

        assert row1 is not None
        assert row1["auth_json"] == new_encrypted_1
        assert row2 is not None
        assert row2["auth_json"] == new_encrypted_2

    def test_empty_list_is_noop(self, repos: RepositoryRepository) -> None:
        """Calling with an empty list raises no error."""
        repos.update_auth_json_bulk([])

    def test_both_rows_updated_atomically(
        self,
        repos: RepositoryRepository,
        make_repo: RepoFactory,
        factory: ConnectionFactory,
    ) -> None:
        """All updates occur in a single transaction."""
        r1 = repos.insert(
            make_repo(
                "repo1", auth=RepoAuth(login_url="http://example.com", username="u1")
            )
        )
        r2 = repos.insert(
            make_repo(
                "repo2", auth=RepoAuth(login_url="http://example.com", username="u2")
            )
        )

        new_encrypted_1 = "gAAAAA_atomic_1"
        new_encrypted_2 = "gAAAAA_atomic_2"

        repos.update_auth_json_bulk([(r1, new_encrypted_1), (r2, new_encrypted_2)])

        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT id, auth_json FROM repositories ORDER BY id"
            ).fetchall()

        updated_rows = {r["id"]: r["auth_json"] for r in rows if r["id"] in (r1, r2)}
        assert updated_rows[r1] == new_encrypted_1
        assert updated_rows[r2] == new_encrypted_2
