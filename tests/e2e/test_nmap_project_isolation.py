"""End-to-end tests for nmap project isolation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import FindingIngestor, RAGEngine
from core.config import ConfigManager
from core.config.schemas import NmapProfile
from domain.tools.base import ToolResult
from tests.conftest import requires_ollama

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]


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
# Scenario 8 – Project isolation  (@requires_ollama)
# ---------------------------------------------------------------------------


@requires_ollama
class TestProjectIsolation:
    def _make_two_projects(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        pm = ProjectManager(base_path=str(tmp_path))
        for n in ("proj-a", "proj-b"):
            pm.create_project_dirs(n)
            pm.save_project(n, [])

    def test_new_project_starts_empty(self, tmp_path: Path) -> None:
        self._make_two_projects(tmp_path)
        engine_a = RAGEngine(project_name="proj-a", base_path=str(tmp_path))
        engine_b = RAGEngine(project_name="proj-b", base_path=str(tmp_path))
        try:
            assert engine_a.collection_name != engine_b.collection_name
            assert engine_b.count_documents() == 0
        finally:
            engine_a.close()
            engine_b.close()

    def test_ingest_does_not_leak_to_other_project(self, tmp_path: Path) -> None:
        self._make_two_projects(tmp_path)
        count = _ingest(tmp_path, "proj-a", _make_nmap_result())
        assert len(count) >= 1
        engine_b = RAGEngine(project_name="proj-b", base_path=str(tmp_path))
        try:
            assert engine_b.count_documents() == 0
        finally:
            engine_b.close()
