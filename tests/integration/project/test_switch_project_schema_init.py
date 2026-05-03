"""Integration test: ``switch_project`` (re)initializes the findings.db schema.

Pins the contract that selecting a project rebuilds the per-project schema
when the database has been dropped or only partially exists, so users can
recover from a hand-deleted ``findings.db`` simply by re-loading the project.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.project.manager import ProjectManager
from domain.projects.entry import ProjectRow
from infrastructure.store.connection import ConnectionFactory

pytestmark = pytest.mark.integration


def _make_project_dir(tmp_path: Path, name: str = "testproject") -> Path:
    proj_dir = tmp_path / "projects" / name
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


def _registry_for(proj_dir: Path, name: str) -> MagicMock:
    registry = MagicMock()
    row = ProjectRow(
        id=1,
        name=name,
        path=str(proj_dir),
        created_at="2024-01-01T00:00:00Z",
    )
    registry.resolve_by_name.return_value = row
    registry.resolve_by_id.return_value = row
    return registry


def _table_names(db_path: Path) -> set[str]:
    factory = ConnectionFactory(db_path)
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def test_switch_project_creates_schema_when_db_missing(tmp_path: Path) -> None:
    proj_dir = _make_project_dir(tmp_path)
    db_path = proj_dir / "sqlite" / "findings.db"
    assert not db_path.exists()

    manager = ProjectManager(
        base_path=str(tmp_path),
        registry=_registry_for(proj_dir, "testproject"),
    )
    manager.switch_project("testproject")

    assert db_path.exists()
    tables = _table_names(db_path)
    assert "findings" in tables
    assert "drafts" in tables
    assert "scan_runs" in tables


def test_switch_project_restores_schema_for_empty_db(tmp_path: Path) -> None:
    """Calling switch_project on a hand-truncated DB rebuilds the tables."""
    proj_dir = _make_project_dir(tmp_path)
    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    db_path.touch()
    assert _table_names(db_path) == set()

    manager = ProjectManager(
        base_path=str(tmp_path),
        registry=_registry_for(proj_dir, "testproject"),
    )
    manager.switch_project("testproject")

    assert "findings" in _table_names(db_path)


def test_switch_project_idempotent_on_existing_schema(tmp_path: Path) -> None:
    """Switching a project that already has full schema is a no-op."""
    proj_dir = _make_project_dir(tmp_path)
    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    ConnectionFactory(db_path).init_schema()
    before = _table_names(db_path)

    manager = ProjectManager(
        base_path=str(tmp_path),
        registry=_registry_for(proj_dir, "testproject"),
    )
    manager.switch_project("testproject")

    assert _table_names(db_path) == before
