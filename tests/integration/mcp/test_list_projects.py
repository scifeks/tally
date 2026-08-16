"""Tests for list_active_projects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.mcp.ingest_service import list_active_projects
from application.ports.run_repository import RunRepositoryPort
from application.project.registry_service import ProjectRegistryService
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.project_registry import ProjectRegistryRepository
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration


def _seed_project_dir(base: Path, name: str) -> Path:
    project_dir = base / "projects" / name
    (project_dir / "config").mkdir(parents=True)
    (project_dir / "config" / "project.json").write_text(
        json.dumps({"project_name": name, "repositories": []})
    )
    return project_dir


def _run_repo_factory(db_path: str) -> RunRepositoryPort:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn_factory = ConnectionFactory(db_file)
    conn_factory.init_schema()
    return RunRepository(conn_factory)


class TestListActiveProjects:
    def test_excludes_archived_projects(self, tmp_path: Path) -> None:
        registry_repo = ProjectRegistryRepository(tmp_path / "tally.db")
        registry_repo.init_schema()

        _seed_project_dir(tmp_path, "active_proj")
        _seed_project_dir(tmp_path, "archived_proj")

        registry_repo.insert(
            "active_proj",
            str((tmp_path / "projects" / "active_proj").resolve()),
        )
        registry_repo.insert(
            "archived_proj",
            str((tmp_path / "projects" / "archived_proj").resolve()),
        )
        registry_repo.archive("archived_proj")

        registry_service = ProjectRegistryService(registry_repo)
        result = list_active_projects(registry_service, _run_repo_factory)

        names = [p["project_name"] for p in result]
        assert "active_proj" in names
        assert "archived_proj" not in names

    def test_returns_correct_fields(self, tmp_path: Path) -> None:
        registry_repo = ProjectRegistryRepository(tmp_path / "tally.db")
        registry_repo.init_schema()

        _seed_project_dir(tmp_path, "test_proj")
        proj_id = registry_repo.insert(
            "test_proj",
            str((tmp_path / "projects" / "test_proj").resolve()),
        )

        registry_service = ProjectRegistryService(registry_repo)
        result = list_active_projects(registry_service, _run_repo_factory)

        assert len(result) == 1
        entry = result[0]
        assert entry["project_id"] == proj_id
        assert entry["project_name"] == "test_proj"
        assert entry["path"] == str((tmp_path / "projects" / "test_proj").resolve())
        assert entry["latest_run_id"] is None

    def test_returns_latest_run_id_when_seeded(self, tmp_path: Path) -> None:
        registry_repo = ProjectRegistryRepository(tmp_path / "tally.db")
        registry_repo.init_schema()

        _seed_project_dir(tmp_path, "test_proj")
        proj_id = registry_repo.insert(
            "test_proj",
            str((tmp_path / "projects" / "test_proj").resolve()),
        )

        row = registry_repo.get_by_id(proj_id)
        assert row is not None
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        conn_factory = ConnectionFactory(paths.findings_db)
        conn_factory.init_schema()
        run_repo = RunRepository(conn_factory)
        run_id = run_repo.create(
            project_id=proj_id,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )

        registry_service = ProjectRegistryService(registry_repo)
        result = list_active_projects(registry_service, _run_repo_factory)

        assert len(result) == 1
        assert result[0]["latest_run_id"] == run_id

    def test_multiple_projects(self, tmp_path: Path) -> None:
        registry_repo = ProjectRegistryRepository(tmp_path / "tally.db")
        registry_repo.init_schema()

        for name in ["proj1", "proj2", "proj3"]:
            _seed_project_dir(tmp_path, name)
            registry_repo.insert(name, str((tmp_path / "projects" / name).resolve()))

        registry_service = ProjectRegistryService(registry_repo)
        result = list_active_projects(registry_service, _run_repo_factory)

        assert len(result) == 3
        names = sorted(p["project_name"] for p in result)
        assert names == ["proj1", "proj2", "proj3"]
