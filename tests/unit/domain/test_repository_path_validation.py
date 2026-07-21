"""Verify Repository tolerates missing paths at construction time."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.project.repositories_service import (
    ProjectRepositoriesService,
    RepositoryPathNotFound,
)
from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import Repository


def _service() -> RepoService:
    return RepoService(name="svc", type=["api"], languages=["python"])


class TestRepositoryAcceptsPath:
    def test_repository_accepts_nonexistent_path(self) -> None:
        repo = Repository(
            name="ghost",
            path="/no/such/path/anywhere",
            services=[_service()],
        )
        assert repo.path == "/no/such/path/anywhere"

    def test_repository_accepts_empty_path(self) -> None:
        repo = Repository(
            name="docker-only",
            path="",
            services=[
                RepoService(
                    name="svc",
                    type=["api"],
                    languages=["python"],
                    docker_path="/app",
                    container_name="ctr",
                )
            ],
        )
        assert repo.path == ""


class TestServiceRejectsNonexistentPath:
    def test_create_rejects_nonexistent_path(self) -> None:
        mock_registry = MagicMock()
        mock_registry.resolve_by_id.return_value = MagicMock(
            archived_at=None, name="proj", path="/tmp/proj"
        )

        mock_repo_repo = MagicMock()
        mock_repo_repo.get_by_name.return_value = None

        service = ProjectRepositoriesService(
            registry=mock_registry,
            config_manager=MagicMock(),
            repo_factory=lambda _: mock_repo_repo,
        )

        repo = Repository(
            name="bad-path",
            path="/no/such/path/anywhere",
            services=[_service()],
        )
        with pytest.raises(RepositoryPathNotFound, match="does not exist"):
            service.create(project_id=1, repo=repo)

    def test_create_accepts_empty_path(self) -> None:
        mock_registry = MagicMock()
        mock_registry.resolve_by_id.return_value = MagicMock(
            archived_at=None, name="proj", path="/tmp/proj"
        )

        mock_repo_repo = MagicMock()
        mock_repo_repo.get_by_name.return_value = None
        mock_repo_repo.insert.return_value = 123
        mock_repo_repo.get_by_id.return_value = Repository(
            name="docker-only",
            path="",
            services=[_service()],
            id=123,
        )

        service = ProjectRepositoriesService(
            registry=mock_registry,
            config_manager=MagicMock(),
            repo_factory=lambda _: mock_repo_repo,
        )

        repo = Repository(
            name="docker-only",
            path="",
            services=[_service()],
        )
        result = service.create(project_id=1, repo=repo)
        assert result.path == ""
