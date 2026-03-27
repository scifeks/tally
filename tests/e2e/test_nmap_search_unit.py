"""End-to-end tests for nmap search (unit, no binary required)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from application.rag.ingestor import ToolHandlerFactory
from application.rag.query import QueryEngine
from core.config import ConfigManager
from core.config.schemas import NmapProfile
from domain.tools.base import ToolResult
from tests.conftest import requires_ollama

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]
_TIMESTAMP = "2024-01-01T00:00:00"


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
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


def _make_rag_engine(base_path: Path, project_name: str) -> RAGEngine:
    return RAGEngine(project_name=project_name, base_path=str(base_path))


def _ingest(
    base_path: Path,
    project_name: str,
    result: ToolResult,
    profile: str = "localhost",
) -> list[dict]:
    """Normalize rows and add rendered text to ChromaDB for search tests."""
    if not result.success or not result.parsed_data:
        return []
    handler = ToolHandlerFactory.load(result.tool_name)
    if handler is None:
        return []
    rows = handler.normalize(result, profile=profile)
    if not rows:
        return []
    engine = _make_rag_engine(base_path, project_name)
    try:
        texts = [handler.render(row) for row in rows]
        metadatas = [{"tool": row["tool"], "profile": row["profile"]} for row in rows]
        ids = [f"{row['profile']}-{row['ip_address']}:{row['port']}" for row in rows]
        engine.add_documents(texts, metadatas, ids)
    finally:
        engine.close()
    return rows


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
# Scenario 5a – Search unit  (@requires_ollama, no nmap, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestSearchUnit:
    def test_search_empty_collection_returns_empty(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        assert qe.search("anything") == []

    def test_search_blank_query_returns_empty(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        assert qe.search("   ") == []

    def test_search_results_have_required_keys(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_nmap_result())
        results = QueryEngine(_make_rag_engine(base, name)).search("127.0.0.1")
        assert len(results) > 0
        for r in results:
            assert "document" in r
            assert "metadata" in r
            assert "distance" in r

    def test_search_results_sorted_by_distance(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_nmap_result())
        results = QueryEngine(_make_rag_engine(base, name)).search("host port open")
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances)
