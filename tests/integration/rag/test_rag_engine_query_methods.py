"""Integration tests for RAGEngine query/get methods."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import ProjectManager  # noqa: E402
from application.rag import RAGEngine  # noqa: E402

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _write_commands_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "nmap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/nmap",
                },
            }
        )
    )


def _make_engine(project_env: dict) -> RAGEngine:
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        return RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


class TestRagEngineQueryMethods:
    def test_query_collection_returns_dict_with_documents_key(
        self, project_env: dict
    ) -> None:
        engine = _make_engine(project_env)
        engine.add_documents(
            texts=["port 80 open on 10.0.0.1", "port 443 open on 10.0.0.2"],
            metadatas=[{"tool": "nmap"}, {"tool": "nmap"}],
            ids=["qc-001", "qc-002"],
        )
        result = engine.query_collection(
            query_texts=["port 80"], n_results=2, include=["documents"]
        )
        assert isinstance(result, dict)
        assert "documents" in result
        assert result["documents"]

    def test_query_collection_returns_empty_dict_when_no_collection(
        self, project_env: dict
    ) -> None:
        engine = _make_engine(project_env)
        engine._collection = None
        assert engine.query_collection(query_texts=["x"]) == {}

    def test_get_documents_returns_seeded_ids(self, project_env: dict) -> None:
        engine = _make_engine(project_env)
        engine.add_documents(
            texts=["finding one", "finding two"],
            metadatas=[{"tool": "nmap"}, {"tool": "nmap"}],
            ids=["gd-001", "gd-002"],
        )
        result = engine.get_documents(ids=["gd-001"], include=["documents"])
        assert "gd-001" in result["ids"]

    def test_get_documents_returns_empty_dict_when_no_collection(
        self, project_env: dict
    ) -> None:
        engine = _make_engine(project_env)
        engine._collection = None
        assert engine.get_documents() == {}

    def test_get_all_metadatas_returns_list_of_dicts(self, project_env: dict) -> None:
        engine = _make_engine(project_env)
        engine.add_documents(
            texts=["nmap result", "semgrep result"],
            metadatas=[{"tool": "nmap"}, {"tool": "semgrep"}],
            ids=["gam-001", "gam-002"],
        )
        metadatas = engine.get_all_metadatas()
        assert isinstance(metadatas, list)
        assert len(metadatas) == 2
        assert all("tool" in m for m in metadatas)

    def test_get_all_metadatas_returns_empty_list_when_no_collection(
        self, project_env: dict
    ) -> None:
        engine = _make_engine(project_env)
        engine._collection = None
        assert engine.get_all_metadatas() == []

    # ------------------------------------------------------------------
    # RAG-1: delete_findings(None, None) removes all documents
    # ------------------------------------------------------------------

    def test_delete_findings_both_none_deletes_all(self, project_env: dict) -> None:
        """delete_findings(tool=None, profile=None) removes all documents."""
        engine = _make_engine(project_env)
        engine.add_documents(
            texts=["nmap result", "semgrep result", "gitleaks result"],
            metadatas=[
                {"tool": "nmap", "profile": "default"},
                {"tool": "semgrep", "profile": "default"},
                {"tool": "gitleaks", "profile": "default"},
            ],
            ids=["del-001", "del-002", "del-003"],
        )
        assert engine.count_documents() == 3
        engine.delete_findings(tool=None, profile=None)
        assert engine.count_documents() == 0

    # ------------------------------------------------------------------
    # RAG-2: get_stats() returns correct structure and counts
    # ------------------------------------------------------------------

    def test_get_stats_reflects_tool_and_severity_counts(
        self, project_env: dict
    ) -> None:
        """get_stats() reports total_documents, by_tool, and by_severity."""
        engine = _make_engine(project_env)
        engine.add_documents(
            texts=["nmap high", "nmap low", "semgrep critical"],
            metadatas=[
                {"tool": "nmap", "severity": "high"},
                {"tool": "nmap", "severity": "low"},
                {"tool": "semgrep", "severity": "critical"},
            ],
            ids=["gs-001", "gs-002", "gs-003"],
        )
        stats = engine.get_stats()
        assert stats["total_documents"] == 3
        assert stats["by_tool"].get("nmap") == 2
        assert stats["by_tool"].get("semgrep") == 1
        assert stats["by_severity"].get("high") == 1
        assert stats["by_severity"].get("low") == 1
        assert stats["by_severity"].get("critical") == 1

    # ------------------------------------------------------------------
    # RAG-3: close() is idempotent — calling twice does not raise
    # ------------------------------------------------------------------

    def test_close_twice_does_not_raise(self, project_env: dict) -> None:
        """Calling close() twice does not raise an exception."""
        engine = _make_engine(project_env)
        engine.close()
        engine.close()  # Should not raise

    # ------------------------------------------------------------------
    # RAG-4: query_collection with n_results > collection size
    # ------------------------------------------------------------------

    def test_search_n_results_larger_than_collection(self, project_env: dict) -> None:
        """query_collection with n_results > doc count returns all docs."""
        engine = _make_engine(project_env)
        engine.add_documents(
            texts=["doc one", "doc two", "doc three"],
            metadatas=[
                {"tool": "nmap"},
                {"tool": "nmap"},
                {"tool": "nmap"},
            ],
            ids=["nr-001", "nr-002", "nr-003"],
        )
        result = engine.query_collection(query_texts=["test"], n_results=1000)
        docs = result.get("documents", [[]])[0]
        assert len(docs) == 3
