"""Tests for ProjectRepositoriesService against a real per-project DB."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.project.repositories_service import (
    ProjectNotFound,
    ProjectRepositoriesService,
    RepoLookupResult,
)
from core.config import Repository
from core.config.manager import ConfigManager
from core.config.schemas.repo_service import RepoService
from domain.projects.entry import ProjectRow
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository

pytestmark = pytest.mark.integration


def _make_repo(*, name: str) -> Repository:
    return Repository(
        name=name,
        services=[
            RepoService(
                name=f"{name}-service",
                type=["api"],
                languages=["python"],
                docker_path="/app",
                container_name="ctr",
            )
        ],
    )


class _FakeRegistry:
    def __init__(self, rows: dict[int, ProjectRow]) -> None:
        self._rows = rows

    def resolve_by_id(self, project_id: int) -> ProjectRow | None:
        return self._rows.get(project_id)


@pytest.fixture
def alpha_path(tmp_path: Path) -> Path:
    p = tmp_path / "projects" / "alpha"
    (p / "sqlite").mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def beta_path(tmp_path: Path) -> Path:
    p = tmp_path / "projects" / "beta"
    (p / "sqlite").mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def registry(alpha_path: Path, beta_path: Path) -> _FakeRegistry:
    return _FakeRegistry(
        rows={
            1: ProjectRow(
                id=1,
                name="alpha",
                path=str(alpha_path),
                created_at="2026-01-01T00:00:00Z",
            ),
            2: ProjectRow(
                id=2,
                name="beta",
                path=str(beta_path),
                created_at="2026-01-01T00:00:00Z",
            ),
            99: ProjectRow(
                id=99,
                name="archived-proj",
                path=str(alpha_path),
                created_at="2026-01-01T00:00:00Z",
                archived_at="2026-01-01",
            ),
        }
    )


@pytest.fixture
def config_manager(tmp_path: Path) -> ConfigManager:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text("{}")
    return ConfigManager(str(tmp_path))


@pytest.fixture
def service(
    registry: _FakeRegistry,
    config_manager: ConfigManager,
    alpha_path: Path,
) -> ProjectRepositoriesService:
    factory = ConnectionFactory(alpha_path / "sqlite" / "findings.db")
    factory.init_schema()
    repo_repo = RepositoryRepository(factory)
    repo_repo.insert(_make_repo(name="api"))
    repo_repo.insert(_make_repo(name="frontend"))
    return ProjectRepositoriesService(registry, config_manager)  # type: ignore[arg-type]


def test_list_active_returns_repos_in_order(
    service: ProjectRepositoriesService,
) -> None:
    repos = service.list_active(1)
    assert [r.name for r in repos] == ["api", "frontend"]
    assert all(r.id is not None for r in repos)


def test_list_active_returns_empty_when_project_has_no_repos(
    service: ProjectRepositoriesService,
) -> None:
    assert service.list_active(2) == []


def test_list_active_raises_for_unknown_project(
    service: ProjectRepositoriesService,
) -> None:
    with pytest.raises(ProjectNotFound):
        service.list_active(404)


def test_list_active_raises_for_archived_project(
    service: ProjectRepositoriesService,
) -> None:
    with pytest.raises(ProjectNotFound):
        service.list_active(99)


def test_find_by_ids_hits_active_repos(
    service: ProjectRepositoriesService,
) -> None:
    repos = service.list_active(1)
    api_id = next(r.id for r in repos if r.name == "api")
    frontend_id = next(r.id for r in repos if r.name == "frontend")
    assert api_id is not None and frontend_id is not None

    result = service.find_by_ids(1, [api_id, frontend_id])
    assert isinstance(result, RepoLookupResult)
    assert sorted(result.found.keys()) == sorted([api_id, frontend_id])
    assert result.missing == []
    assert result.available == sorted([api_id, frontend_id])


def test_find_by_ids_reports_unknown_ids(
    service: ProjectRepositoriesService,
) -> None:
    repos = service.list_active(1)
    api_id = next(r.id for r in repos if r.name == "api")
    assert api_id is not None
    result = service.find_by_ids(1, [api_id, 9999])
    assert list(result.found.keys()) == [api_id]
    assert result.missing == [9999]


def test_find_by_ids_empty_input_returns_empty_lookup(
    service: ProjectRepositoriesService,
) -> None:
    result = service.find_by_ids(1, [])
    assert result.found == {}
    assert result.missing == []


def test_find_by_ids_preserves_caller_order_in_found(
    service: ProjectRepositoriesService,
) -> None:
    repos = service.list_active(1)
    api_id = next(r.id for r in repos if r.name == "api")
    frontend_id = next(r.id for r in repos if r.name == "frontend")
    assert api_id is not None and frontend_id is not None

    result = service.find_by_ids(1, [frontend_id, api_id])
    assert list(result.found.keys()) == [frontend_id, api_id]


def test_find_by_ids_raises_for_unknown_project(
    service: ProjectRepositoriesService,
) -> None:
    with pytest.raises(ProjectNotFound):
        service.find_by_ids(404, [10])
