"""Integration tests for gitleaks project creation (no external dependencies)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from core.config import ConfigManager
from core.config.schemas import CommandEntry

pytestmark = pytest.mark.integration

_TALLY_ROOT = Path(__file__).resolve().parents[3]


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _write_commands_config(base_path: Path) -> None:
    cm = ConfigManager(base_path=str(base_path))
    cm.save_commands_config(
        {
            "gitleaks": CommandEntry(
                type="repo",
                location="local",
                path=shutil.which("gitleaks") or "/usr/local/bin/gitleaks",
            ),
        }
    )


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    """Minimal project environment under tmp_path (no data)."""
    name = "test-gitleaks-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name)
    return {"base_path": tmp_path, "project_name": name}


class TestProjectCreation:
    def test_project_dirs_created(self, project_env: dict) -> None:
        root = project_env["base_path"] / "projects" / project_env["project_name"]
        expected = [
            root / "config" / "endpoints",
            root / "chroma_db",
            root / "tool_outputs" / "semgrep",
            root / "tool_outputs" / "osv-scanner",
            root / "tool_outputs" / "gitleaks",
            root / "tool_outputs" / "zap",
            root / "sessions",
        ]
        for d in expected:
            assert d.is_dir(), f"Missing: {d}"

    def test_project_config_written(self, project_env: dict) -> None:
        p = (
            project_env["base_path"]
            / "projects"
            / project_env["project_name"]
            / "config"
            / "project.json"
        )
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["project_name"] == project_env["project_name"]
        assert "created" in data

    def test_project_listed_by_manager(self, project_env: dict) -> None:
        pm = ProjectManager(base_path=str(project_env["base_path"]))
        assert project_env["project_name"] in pm.list_projects()
