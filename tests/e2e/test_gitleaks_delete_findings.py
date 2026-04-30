"""End-to-end tests for gitleaks delete_findings behaviour."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from core.config import ConfigManager
from core.config.schemas import CommandEntry
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


def _make_rag_engine(base_path: Path, project_name: str) -> RAGEngine:
    return RAGEngine(project_name=project_name, base_path=str(base_path))


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
    pm.save_project(name)
    return {"base_path": tmp_path, "project_name": name}


# ---------------------------------------------------------------------------
# Scenario 4b – delete_findings  (@requires_ollama, no gitleaks, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestDeleteFindings:
    def _add_docs(self, engine: RAGEngine, profile: str, ids: list[str]) -> None:
        ts = RAGEngine.now_iso()
        engine.add_documents(
            texts=[f"Secret in repo ({profile})" for _ in ids],
            metadatas=[
                {
                    "tool": "gitleaks",
                    "profile": profile,
                    "finding_type": "secret",
                    "timestamp": ts,
                }
                for _ in ids
            ],
            ids=ids,
        )

    def test_delete_by_tool_and_profile(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "my-repo", ["doc-a", "doc-b"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("gitleaks", "my-repo")

        assert deleted == 2
        assert engine.count_documents() == 0

    def test_delete_scoped_to_profile_leaves_others(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "repo-a", ["a-1"])
        self._add_docs(engine, "repo-b", ["b-1"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("gitleaks", "repo-a")

        assert deleted == 1
        assert engine.count_documents() == 1

    def test_delete_by_tool_only_removes_all_profiles(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "repo-a", ["a-1"])
        self._add_docs(engine, "repo-b", ["b-1"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("gitleaks")

        assert deleted == 2
        assert engine.count_documents() == 0

    def test_delete_nonexistent_returns_zero(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        assert engine.count_documents() == 0

        deleted = engine.delete_findings("gitleaks", "my-repo")

        assert deleted == 0
