"""End-to-end tests for gitleaks chat (unit, no binary required)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from application.rag.query import QueryEngine
from core.config import ConfigManager
from core.config.schemas import CommandEntry
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


def _make_gitleaks_result() -> ToolResult:
    """Synthetic single-secret ToolResult. No gitleaks binary needed."""
    return ToolResult(
        tool_name="gitleaks",
        success=True,
        output="",
        parsed_data={
            "secrets": [
                {
                    "rule_id": "aws-access-token",
                    "description": "AWS Access Token",
                    "file_path": "config/aws.js",
                    "line_number": 10,
                    "commit": "",
                    "tags": [],
                    "fingerprint": "config/aws.js:aws-access-token:10",
                    "secret": "AKIAXYZ3FGHLMN2PQRST",
                    "match": "AKIAXYZ3FGHLMN2PQRST",
                }
            ],
            "summary": {
                "total_secrets": 1,
                "by_rule": {"aws-access-token": 1},
                "files_with_secrets": 1,
            },
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
    repo: str | None = None,
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
    bus.dispatch(
        ToolCompleted(result, profile, None, project_name, str(base_path), repo=repo)
    )
    return ids


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Scenario 6a – Chat unit  (@requires_ollama, no gitleaks, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestChatUnit:
    def test_chat_no_data_returns_informative_message(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            response = QueryEngine(engine).chat("what secrets were found?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert "No relevant findings" in response

    def test_chat_blank_message_returns_prompt(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            response = QueryEngine(engine).chat("   ")
        finally:
            engine.close()
        assert "Please provide a message" in response

    def test_chat_with_data_returns_non_empty_string(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        ids = _run_pipeline(base, name, _make_gitleaks_result(), profile="my-test-repo")
        assert len(ids) > 0, "pipeline produced 0 SQLite rows for gitleaks"
        engine = _make_rag_engine(base, name)
        try:
            assert engine.count_documents() == len(ids), (
                f"ChromaDB doc count {engine.count_documents()} "
                f"!= SQLite row count {len(ids)}"
            )
            response = QueryEngine(engine).chat("what secrets were detected?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert len(response) > 0
