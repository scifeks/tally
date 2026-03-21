"""Integration tests for gitleaks commands.json configuration (no external deps)."""

from __future__ import annotations

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
            "nmap": CommandEntry(
                type="repo",
                location="local",
                path=shutil.which("nmap") or "/usr/bin/nmap",
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
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


class TestGitleaksCommandsConfig:
    def test_commands_config_round_trips(self, project_env: dict) -> None:
        base = project_env["base_path"]
        loaded = ConfigManager(base_path=str(base)).load_commands_config()
        assert loaded is not None
        assert "gitleaks" in loaded
        assert loaded["gitleaks"].type == "repo"
        assert loaded["gitleaks"].location == "local"
