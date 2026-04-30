"""Unit tests for ProjectRepositoriesService."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from application.project.repositories_service import (
    ProjectNotFound,
    ProjectRepositoriesService,
    RepoLookupResult,
)
from core.config import Repository


def _make_repo(*, base: Path, name: str, repo_id: int | None) -> Repository:
    repo_path = base / name
    repo_path.mkdir(parents=True, exist_ok=True)
    return Repository(
        name=name,
        uuid=str(uuid4()),
        id=repo_id,
        type=["api"],
        path=str(repo_path),
        languages=["python"],
    )


class _FakeRegistry:
    def __init__(self, rows: dict[int, dict[str, Any]]) -> None:
        self._rows = rows

    def resolve_by_id(self, project_id: int) -> dict[str, Any] | None:
        return self._rows.get(project_id)


class _FakeConfigManager:
    def __init__(self, repos_by_project: dict[str, list[Repository]]) -> None:
        self._repos_by_project = repos_by_project
        self.calls: list[str] = []

    def load_repositories(self, project_name: str) -> list[Repository]:
        self.calls.append(project_name)
        return list(self._repos_by_project.get(project_name, []))


@pytest.fixture
def registry() -> _FakeRegistry:
    return _FakeRegistry(
        rows={
            1: {"id": 1, "name": "alpha", "archived_at": None},
            2: {"id": 2, "name": "beta", "archived_at": None},
            99: {"id": 99, "name": "archived-proj", "archived_at": "2026-01-01"},
        }
    )


@pytest.fixture
def config_manager(tmp_path: Path) -> _FakeConfigManager:
    return _FakeConfigManager(
        repos_by_project={
            "alpha": [
                _make_repo(base=tmp_path, name="api", repo_id=10),
                _make_repo(base=tmp_path, name="frontend", repo_id=20),
                _make_repo(base=tmp_path, name="ghost", repo_id=None),
            ],
            "beta": [],
        }
    )


@pytest.fixture
def service(
    registry: _FakeRegistry, config_manager: _FakeConfigManager
) -> ProjectRepositoriesService:
    return ProjectRepositoriesService(registry, config_manager)  # type: ignore[arg-type]


def test_list_active_returns_only_db_resident_repos(
    service: ProjectRepositoriesService,
) -> None:
    repos = service.list_active(1)
    assert [r.id for r in repos] == [10, 20]
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
    result = service.find_by_ids(1, [10, 20])
    assert isinstance(result, RepoLookupResult)
    assert sorted(result.found.keys()) == [10, 20]
    assert result.found[10].name == "api"
    assert result.missing == []
    assert result.available == [10, 20]


def test_find_by_ids_reports_unknown_ids(
    service: ProjectRepositoriesService,
) -> None:
    result = service.find_by_ids(1, [10, 9999])
    assert list(result.found.keys()) == [10]
    assert result.missing == [9999]
    assert result.available == [10, 20]


def test_find_by_ids_excludes_repos_without_db_id(
    service: ProjectRepositoriesService,
) -> None:
    # The 'ghost' repo in fixture has id=None and must not be considered valid.
    ghost_id_marker = -1
    result = service.find_by_ids(1, [ghost_id_marker])
    assert result.found == {}
    assert result.missing == [ghost_id_marker]
    assert result.available == [10, 20]


def test_find_by_ids_empty_input_returns_empty_lookup(
    service: ProjectRepositoriesService,
) -> None:
    result = service.find_by_ids(1, [])
    assert result.found == {}
    assert result.missing == []
    assert result.available == [10, 20]


def test_find_by_ids_preserves_caller_order_in_found(
    service: ProjectRepositoriesService,
) -> None:
    result = service.find_by_ids(1, [20, 10])
    assert list(result.found.keys()) == [20, 10]


def test_find_by_ids_raises_for_unknown_project(
    service: ProjectRepositoriesService,
) -> None:
    with pytest.raises(ProjectNotFound):
        service.find_by_ids(404, [10])
