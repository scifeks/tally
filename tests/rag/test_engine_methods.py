"""Tests for RAGEngine.get_document_by_id and update_metadata methods."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.project import ProjectManager  # noqa: E402
from core.rag import RAGEngine  # noqa: E402

_OLLAMA_URL = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_global_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama_base_url": _OLLAMA_URL,
                "default_llm": "qwen3:14b",
                "default_embedding": "nomic-embed-text:latest",
            }
        )
    )


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm._create_project_dirs(name)
    pm._save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


# ---------------------------------------------------------------------------
# TestGetDocumentById
# ---------------------------------------------------------------------------


class TestGetDocumentById:
    def test_returns_correct_document(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["open port 80 on 10.0.0.1"],
            metadatas=[{"tool": "nmap"}],
            ids=["doc-001"],
        )
        doc = engine.get_document_by_id("doc-001")
        assert doc is not None
        assert doc["id"] == "doc-001"
        assert "port 80" in doc["document"]
        assert doc["metadata"]["tool"] == "nmap"

    def test_returns_none_for_unknown_id(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        result = engine.get_document_by_id("nonexistent-id")
        assert result is None

    def test_document_key_is_string(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["some finding text"],
            metadatas=[{"tool": "nmap"}],
            ids=["doc-str-001"],
        )
        doc = engine.get_document_by_id("doc-str-001")
        assert doc is not None
        assert isinstance(doc["document"], str)

    def test_metadata_key_is_dict(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["some finding text"],
            metadatas=[{"tool": "nmap"}],
            ids=["doc-meta-001"],
        )
        doc = engine.get_document_by_id("doc-meta-001")
        assert doc is not None
        assert isinstance(doc["metadata"], dict)


# ---------------------------------------------------------------------------
# TestUpdateMetadata
# ---------------------------------------------------------------------------


class TestUpdateMetadata:
    def test_updates_specified_fields(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["ssh open on 22"],
            metadatas=[{"tool": "nmap"}],
            ids=["upd-001"],
        )
        engine.update_metadata("upd-001", {"enriched": True})
        doc = engine.get_document_by_id("upd-001")
        assert doc is not None
        assert doc["metadata"]["enriched"] is True

    def test_preserves_unrelated_fields(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["ssh open on 22"],
            metadatas=[{"tool": "nmap", "profile": "quick"}],
            ids=["upd-002"],
        )
        engine.update_metadata("upd-002", {"enriched": True})
        doc = engine.get_document_by_id("upd-002")
        assert doc is not None
        assert doc["metadata"]["profile"] == "quick"
        assert doc["metadata"]["enriched"] is True

    def test_raises_for_unknown_id(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        with pytest.raises(ValueError, match="not found"):
            engine.update_metadata("nonexistent", {"enriched": True})

    def test_merge_semantics(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["rdp open on 3389"],
            metadatas=[{"tool": "nmap", "severity": "potential"}],
            ids=["upd-003"],
        )
        engine.update_metadata("upd-003", {"risk_type": "exposed_service"})
        doc = engine.get_document_by_id("upd-003")
        assert doc is not None
        assert doc["metadata"]["tool"] == "nmap"
        assert doc["metadata"]["severity"] == "potential"
        assert doc["metadata"]["risk_type"] == "exposed_service"
