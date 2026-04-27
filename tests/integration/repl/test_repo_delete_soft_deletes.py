"""Integration test: delete_repository soft-deletes the DB row (F3)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository

pytestmark = pytest.mark.integration


def _make_project_dir(tmp_path: Path, repo_uuid: str) -> Path:
    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    project_config = {
        "project_name": "Test Project",
        "created": "2024-01-01T00:00:00",
        "abbreviation": "TP",
        "company_name": "Acme",
        "department_name": "Security",
        "repositories": [
            {
                "name": "myrepo",
                "uuid": repo_uuid,
                "type": ["api"],
                "path": str(tmp_path),
                "languages": ["python"],
            }
        ],
    }
    (proj_dir / "config" / "project.json").write_text(json.dumps(project_config))

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text("{}")

    return proj_dir


def test_delete_repository_soft_deletes_db_row(tmp_path: Path) -> None:
    """ProjectManager.delete_repository stamps deleted_at on the DB row."""
    from application.project.manager import ProjectManager

    repo_uuid = str(uuid.uuid4())
    proj_dir = _make_project_dir(tmp_path, repo_uuid)

    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    repo_repo = RepositoryRepository(factory)
    repo_repo.insert(uuid=repo_uuid, name="myrepo")

    registry = MagicMock()
    registry.resolve_by_name.return_value = {
        "id": 1,
        "name": "testproject",
        "path": str(proj_dir),
        "archived_at": None,
    }

    manager = ProjectManager(base_path=str(tmp_path), registry=registry)
    manager.delete_repository("testproject", "myrepo")

    row = repo_repo.get_by_uuid_including_deleted(repo_uuid)
    assert row is not None, "DB row should still exist after soft-delete"
    assert row.deleted_at is not None, "deleted_at must be stamped after deletion"
    assert repo_repo.get_by_uuid(repo_uuid) is None, (
        "get_by_uuid must return None for soft-deleted repos"
    )
