"""End-to-end tests for nmap scan execution."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.tools.executor import ToolExecutor
from application.tools.registry import tool_registry
from core.config import ConfigManager
from core.config.schemas import NmapProfile
from domain.tools.base import ToolResult
from tests.conftest import requires_nmap

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]

slow = pytest.mark.slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _run_scan(
    base_path: Path, project_name: str, profile: str = "localhost"
) -> ToolResult:
    tool = tool_registry.get_tool("nmap")
    assert tool is not None
    executor = ToolExecutor(
        project_name=project_name, base_path=base_path, auto_approve=True
    )
    return executor.execute(
        tool,
        label=profile,
        profile=profile,
        project_name=project_name,
        base_path=str(base_path),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    """Minimal project environment under tmp_path (no nmap config, no data)."""
    name = "test-proj"
    _write_global_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


@pytest.fixture()
def nmap_project_env(project_env: dict) -> dict:
    """project_env with a localhost nmap profile pre-configured."""
    _write_nmap_config(project_env["base_path"], project_env["project_name"])
    return project_env


# ---------------------------------------------------------------------------
# Scenario 3 – Nmap scan execution  (@requires_nmap @slow)
# ---------------------------------------------------------------------------


@requires_nmap
@slow
class TestNmapExecution:
    def test_scan_succeeds(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        assert result.success, f"Scan failed: {result.output}"

    def test_output_file_created(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        assert result.output_files
        stdout = result.output_files.get("stdout")
        assert stdout is not None and Path(stdout).exists()

    def test_output_file_is_xml(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        content = Path(result.output_files["stdout"]).read_text()
        assert content.lstrip().startswith("<?xml")

    def test_parsed_data_has_hosts(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        assert result.parsed_data is not None
        assert "error" not in result.parsed_data
        assert "hosts" in result.parsed_data
