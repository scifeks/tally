"""End-to-end tests for gitleaks upsert / no-duplicate re-ingest behaviour."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import FindingIngestor, RAGEngine
from core.config import ConfigManager
from core.config.schemas import CommandEntry
from domain.tools.base import ToolResult
from tests.conftest import requires_ollama

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


def _ingest(
    base_path: Path,
    project_name: str,
    result: ToolResult,
    profile: str = "my-test-repo",
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
    """Minimal project environment under tmp_path (no data)."""
    name = "test-gitleaks-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


# ---------------------------------------------------------------------------
# Scenario 7 – Upsert / no duplicates on re-ingest  (@requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_ollama
@slow
class TestUpsert:
    def test_rescan_does_not_duplicate_documents(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]

        ids1 = _ingest(base, name, _make_gitleaks_result())
        assert len(ids1) >= 1
        engine = _make_rag_engine(base, name)
        try:
            count_after_first = engine.count_documents()
        finally:
            engine.close()

        time.sleep(1)  # force different ts_compact → different IDs in second ingest

        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            count_after_second = engine.count_documents()
        finally:
            engine.close()

        assert count_after_second == count_after_first, (
            f"Document count grew {count_after_first} → {count_after_second}: "
            "delete_findings is not clearing stale docs before re-ingestion"
        )
