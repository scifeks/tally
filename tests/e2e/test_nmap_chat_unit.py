"""End-to-end tests for nmap chat (unit, no binary required)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from application.rag.query import QueryEngine
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
                            "transport": "tcp",
                            "state": "open",
                            "service": "ssh",
                            "service_version": "",
                        },
                        {
                            "port": 80,
                            "transport": "tcp",
                            "state": "open",
                            "service": "http",
                            "service_version": "",
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


def _run_pipeline(
    base_path: Path,
    project_name: str,
    result: ToolResult,
    profile: str,
) -> list[int]:
    """Drive the full ingest pipeline; returns SQLite finding IDs."""
    from application.pipeline.handlers import (
        ChromaDBHandler,
        EnrichmentHandler,
        IngestHandler,
    )
    from domain.pipeline.events import (
        EnrichmentCompleted,
        EventBus,
        IngestCompleted,
        ToolCompleted,
    )

    bus = EventBus()
    ingest = IngestHandler(bus)
    enrich = EnrichmentHandler(bus)
    chroma = ChromaDBHandler()

    bus.subscribe(ToolCompleted, ingest.handle)
    bus.subscribe(IngestCompleted, enrich.handle)
    bus.subscribe(EnrichmentCompleted, chroma.handle)

    ids: list[int] = []

    def _capture(event: IngestCompleted) -> None:
        ids.extend(event.ids)

    bus.subscribe(IngestCompleted, _capture)
    bus.dispatch(ToolCompleted(result, profile, None, project_name, str(base_path)))
    return ids


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
# Scenario 6a – Chat unit  (@requires_ollama, no nmap, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestChatUnit:
    def test_chat_no_data_returns_informative_message(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        response = qe.chat("what hosts were scanned?")
        assert isinstance(response, str)
        assert "No relevant findings" in response

    def test_chat_blank_message_returns_prompt(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        assert "Please provide a message" in qe.chat("   ")

    def test_chat_with_data_returns_non_empty_string(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        ids = _run_pipeline(base, name, _make_nmap_result(), profile=name)
        assert len(ids) > 0, "pipeline produced 0 SQLite rows for nmap"
        engine = _make_rag_engine(base, name)
        try:
            assert engine.count_documents() == len(ids), (
                f"ChromaDB doc count {engine.count_documents()} "
                f"!= SQLite row count {len(ids)}"
            )
            response = QueryEngine(engine).chat("what ports are open?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert len(response) > 0
