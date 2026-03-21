"""End-to-end tests for nmap chat with real binary."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import FindingIngestor, RAGEngine
from application.rag.query import QueryEngine
from application.tools.executor import ToolExecutor
from application.tools.registry import tool_registry
from core.config import ConfigManager
from core.config.schemas import NmapProfile
from domain.tools.base import ToolResult
from tests.conftest import requires_nmap, requires_ollama

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


def _make_nmap_result() -> ToolResult:
    """Synthetic ToolResult with valid parsed nmap data. No nmap binary needed."""
    return ToolResult(
        tool_name="nmap",
        success=True,
        output="",
        parsed_data={
            "hosts": [
                {
                    "ip_address": "127.0.0.1",
                    "hostname": "localhost",
                    "state": "up",
                    "ports": [
                        {
                            "port": 22,
                            "protocol": "tcp",
                            "state": "open",
                            "service": "ssh",
                            "version": "",
                        },
                        {
                            "port": 80,
                            "protocol": "tcp",
                            "state": "open",
                            "service": "http",
                            "version": "",
                        },
                    ],
                }
            ]
        },
        output_files={},
        timestamp=RAGEngine.now_iso(),
        duration_seconds=0.1,
    )


def _make_rag_engine(base_path: Path, project_name: str) -> RAGEngine:
    return RAGEngine(project_name=project_name, base_path=str(base_path))


def _ingest(
    base_path: Path, project_name: str, result: ToolResult, profile: str = "localhost"
) -> list[str]:
    engine = _make_rag_engine(base_path, project_name)
    try:
        return FindingIngestor(engine, project_name).ingest_tool_output(
            result, profile=profile
        )
    finally:
        engine.close()


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
# Scenario 6b – Chat e2e with real nmap  (@requires_nmap @requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_nmap
@requires_ollama
@slow
class TestChatE2E:
    def test_chat_references_scan_data(self, nmap_project_env: dict) -> None:
        base, name = nmap_project_env["base_path"], nmap_project_env["project_name"]
        result = _run_scan(base, name)
        _ingest(base, name, result)
        response = QueryEngine(_make_rag_engine(base, name)).chat(
            "what hosts were scanned?"
        )
        assert isinstance(response, str)
        assert len(response) > 0
