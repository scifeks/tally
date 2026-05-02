"""End-to-end tests for gitleaks delete_findings behaviour."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag.knowledge_base import FindingKnowledgeBase
from core.config import ConfigManager
from core.config.schemas import CommandEntry
from infrastructure.embedding.factory import get_embedding_provider
from infrastructure.llm.factory import get_llm_provider
from infrastructure.vector.factory import make_chromadb_vector_index
from tests.conftest import requires_ollama

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]


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


def _make_kb(base_path: Path, project_name: str) -> FindingKnowledgeBase:
    embedding_provider = get_embedding_provider(base_path)
    chat_provider = get_llm_provider("chat", base_path)
    vector_index = make_chromadb_vector_index(
        project_name=project_name,
        base_path=base_path,
        embedding_provider=embedding_provider,
    )
    return FindingKnowledgeBase(
        vector_index=vector_index,
        chat_provider=chat_provider,
        project_name=project_name,
        base_path=base_path,
    )


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


_FIXED_TIMESTAMP = "2024-01-01T00:00:00"


@requires_ollama
class TestDeleteFindings:
    def _add_docs(self, kb: FindingKnowledgeBase, profile: str, ids: list[str]) -> None:
        kb.add_findings(
            documents=[f"Secret in repo ({profile})" for _ in ids],
            metadatas=[
                {
                    "tool": "gitleaks",
                    "profile": profile,
                    "finding_type": "secret",
                    "timestamp": _FIXED_TIMESTAMP,
                }
                for _ in ids
            ],
            ids=ids,
        )

    def test_delete_by_tool_and_profile(self, project_env: dict) -> None:
        kb = _make_kb(project_env["base_path"], project_env["project_name"])
        self._add_docs(kb, "my-repo", ["doc-a", "doc-b"])
        assert kb.count() == 2

        deleted = kb.delete_findings("gitleaks", "my-repo")

        assert deleted == 2
        assert kb.count() == 0

    def test_delete_scoped_to_profile_leaves_others(self, project_env: dict) -> None:
        kb = _make_kb(project_env["base_path"], project_env["project_name"])
        self._add_docs(kb, "repo-a", ["a-1"])
        self._add_docs(kb, "repo-b", ["b-1"])
        assert kb.count() == 2

        deleted = kb.delete_findings("gitleaks", "repo-a")

        assert deleted == 1
        assert kb.count() == 1

    def test_delete_by_tool_only_removes_all_profiles(self, project_env: dict) -> None:
        kb = _make_kb(project_env["base_path"], project_env["project_name"])
        self._add_docs(kb, "repo-a", ["a-1"])
        self._add_docs(kb, "repo-b", ["b-1"])
        assert kb.count() == 2

        deleted = kb.delete_findings("gitleaks")

        assert deleted == 2
        assert kb.count() == 0

    def test_delete_nonexistent_returns_zero(self, project_env: dict) -> None:
        kb = _make_kb(project_env["base_path"], project_env["project_name"])
        assert kb.count() == 0

        deleted = kb.delete_findings("gitleaks", "my-repo")

        assert deleted == 0
