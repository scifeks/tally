"""Tests for mcp.tools.project.get_project_config."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from tally_mcp.tools import project  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    return tmp_path


def _write_config(root: Path, name: str, data: dict) -> None:
    cfg_dir = root / "projects" / name / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "project.json").write_text(json.dumps(data))


async def test_get_project_config_returns_dict(
    project_root: Path,
) -> None:
    cfg = {
        "name": "myproject",
        "repositories": [{"name": "api", "path": "/repos/api"}],
    }
    _write_config(project_root, "myproject", cfg)

    original = project._app_root
    project._app_root = project_root
    try:
        result = await project.get_project_config("myproject")
    finally:
        project._app_root = original

    assert isinstance(result, dict)
    assert "repositories" in result
    assert result["repositories"][0]["name"] == "api"


async def test_get_project_config_unknown_project_raises_file_not_found(
    project_root: Path,
) -> None:
    original = project._app_root
    project._app_root = project_root
    try:
        with pytest.raises(FileNotFoundError):
            await project.get_project_config("does-not-exist")
    finally:
        project._app_root = original


def _seed_registry(tally_db: Path, name: str, project_path: Path) -> None:
    tally_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tally_db))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            path        TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            ),
            archived_at TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO projects (name, path) VALUES (?, ?)",
        (name, str(project_path)),
    )
    conn.commit()
    conn.close()


async def test_get_project_config_uses_registry_path(
    project_root: Path,
) -> None:
    elsewhere = project_root / "elsewhere" / "myproject"
    cfg_dir = elsewhere / "config"
    cfg_dir.mkdir(parents=True)
    cfg = {"name": "myproject", "repositories": []}
    (cfg_dir / "project.json").write_text(json.dumps(cfg))
    _seed_registry(project_root / "tally.db", "myproject", elsewhere)

    original = project._app_root
    project._app_root = project_root
    try:
        result = await project.get_project_config("myproject")
    finally:
        project._app_root = original

    assert result["name"] == "myproject"
