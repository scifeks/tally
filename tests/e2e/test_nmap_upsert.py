"""End-to-end tests for nmap upsert / no-duplicate re-ingest behaviour."""

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
    """Normalize rows and upsert rendered text into ChromaDB."""
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
# Scenario 7 – Upsert / no duplicates on re-ingest  (@requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_ollama
@slow
class TestUpsert:
    def test_rescan_does_not_duplicate_documents(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]

        rows1 = _ingest(base, name, _make_nmap_result())
        assert len(rows1) >= 1
        total_after_first = _make_rag_engine(base, name).count_documents()

        _ingest(base, name, _make_nmap_result())
        total_after_second = _make_rag_engine(base, name).count_documents()

        assert total_after_second == total_after_first, (
            f"Document count grew {total_after_first} → {total_after_second}: "
            "upsert is not deduplicating on re-ingestion"
        )
