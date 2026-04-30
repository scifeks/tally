"""Integration test: delete_repository soft-deletes the DB row."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config.schemas.repository import Repository
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository

pytestmark = pytest.mark.integration


def _make_project_dir(tmp_path: Path) -> Path:
    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    project_config = {
        "project_name": "Test Project",
        "created": "2024-01-01T00:00:00",
        "abbreviation": "TP",
        "company_name": "Acme",
        "department_name": "Security",
    }
    (proj_dir / "config" / "project.json").write_text(json.dumps(project_config))

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text("{}")

    return proj_dir


def test_delete_repository_soft_deletes_db_row(tmp_path: Path) -> None:
    """ProjectManager.delete_repository stamps deleted_at on the DB row."""
    from application.project.manager import ProjectManager

    proj_dir = _make_project_dir(tmp_path)

    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    repo_repo = RepositoryRepository(factory)
    repo_id = repo_repo.insert(
        Repository(
            name="myrepo",
            type=["api"],
            languages=["python"],
            path=str(tmp_path),
        )
    )

    registry = MagicMock()
    registry.resolve_by_name.return_value = {
        "id": 1,
        "name": "testproject",
        "path": str(proj_dir),
        "archived_at": None,
    }
    registry.resolve_by_id.return_value = {
        "id": 1,
        "name": "testproject",
        "path": str(proj_dir),
        "archived_at": None,
    }

    manager = ProjectManager(base_path=str(tmp_path), registry=registry)
    manager.delete_repository("testproject", "myrepo")

    assert repo_repo.is_deleted(repo_id), "deleted_at must be stamped after deletion"
    assert repo_repo.get_by_name("myrepo") is None, (
        "get_by_name must skip soft-deleted rows"
    )
