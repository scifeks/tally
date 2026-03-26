"""Tests for RAGEngine.add_documents upsert semantics."""

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


def _make_rag_engine(project_env: dict) -> RAGEngine:
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


class TestAddDocumentsUpsert:
    def test_upsert_adds_new_document(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["ssh open on 22"],
            metadatas=[{"tool": "nmap", "profile": "quick"}],
            ids=["upd-001"],
        )
        doc = engine.get_document_by_id("upd-001")
        assert doc is not None
        assert doc["document"] == "ssh open on 22"
        assert doc["metadata"]["tool"] == "nmap"

    def test_upsert_same_id_updates_text(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["ssh open on 22"],
            metadatas=[{"tool": "nmap", "profile": "quick"}],
            ids=["upd-002"],
        )
        engine.add_documents(
            texts=["rdp open on 3389"],
            metadatas=[{"tool": "nmap", "profile": "quick"}],
            ids=["upd-002"],
        )
        doc = engine.get_document_by_id("upd-002")
        assert doc is not None
        assert doc["document"] == "rdp open on 3389"

    def test_upsert_same_id_updates_metadata(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["ssh open on 22"],
            metadatas=[{"tool": "nmap", "profile": "quick"}],
            ids=["upd-003"],
        )
        engine.add_documents(
            texts=["ssh open on 22"],
            metadatas=[{"tool": "nmap", "profile": "full", "severity": "low"}],
            ids=["upd-003"],
        )
        doc = engine.get_document_by_id("upd-003")
        assert doc is not None
        assert doc["metadata"]["profile"] == "full"
        assert doc["metadata"]["severity"] == "low"

    def test_unknown_id_returns_none(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        doc = engine.get_document_by_id("nonexistent")
        assert doc is None
