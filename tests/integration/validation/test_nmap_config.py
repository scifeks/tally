"""Integration tests for nmap project configuration (no external dependencies)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from core.config import ConfigManager
from core.config.schemas import NmapProfile

pytestmark = pytest.mark.integration

_TALLY_ROOT = Path(__file__).resolve().parents[3]


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _write_nmap_config(base_path: Path, project_name: str) -> None:
    cm = ConfigManager(base_path=str(base_path))
    cm.save_nmap_hosts(
        project_name,
        {"localhost": NmapProfile(hosts=["127.0.0.1"], nmap_args="-p 22,80,443")},
    )


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    """Minimal project environment under tmp_path (no nmap config, no data)."""
    name = "test-proj"
    _write_global_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


class TestNmapConfig:
    def test_nmap_profile_round_trips(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _write_nmap_config(base, name)

        nmap_config = ConfigManager(base_path=str(base)).load_nmap_hosts(name)
        assert nmap_config is not None
        assert "localhost" in nmap_config.profiles
        assert "127.0.0.1" in nmap_config.profiles["localhost"].hosts
        assert "-p 22,80,443" in nmap_config.profiles["localhost"].nmap_args
