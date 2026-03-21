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
