"""End-to-end tests for nmap ingestion (unit, no binary required)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from application.rag.ingestor import ToolHandlerFactory
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
    """Normalize rows and embed rendered text into ChromaDB via Ollama."""
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
# Scenario 4a – Ingestion unit tests  (@requires_ollama, no nmap, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestIngestionUnit:
    def test_ingestion_returns_positive_count(self, project_env: dict) -> None:
        rows = _ingest(
            project_env["base_path"], project_env["project_name"], _make_nmap_result()
        )
        assert len(rows) >= 1

    def test_stats_shows_nmap_documents(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_nmap_result())
        engine = _make_rag_engine(base, name)
        try:
            stats = engine.get_stats()
        finally:
            engine.close()
        assert stats["total_documents"] > 0
        assert "nmap" in stats["by_tool"]

    def test_failed_result_not_ingested(self, project_env: dict) -> None:
        failed = ToolResult(
            tool_name="nmap",
            success=False,
            output="denied",
            parsed_data=None,
            output_files={},
            timestamp=_TIMESTAMP,
            duration_seconds=0.0,
        )
        rows = _ingest(project_env["base_path"], project_env["project_name"], failed)
        assert rows == []

    def test_parse_error_result_not_ingested(self, project_env: dict) -> None:
        errored = ToolResult(
            tool_name="nmap",
            success=True,
            output="",
            parsed_data={"error": "malformed XML"},
            output_files={},
            timestamp=_TIMESTAMP,
            duration_seconds=0.0,
        )
        rows = _ingest(project_env["base_path"], project_env["project_name"], errored)
        assert rows == []
