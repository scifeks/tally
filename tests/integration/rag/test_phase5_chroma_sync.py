"""Phase 5 integration tests: sync_finding_to_chroma does a direct id-based upsert."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

from application.rag.engine import RAGEngine
from infrastructure.store import make_store
from infrastructure.store.repositories.findings_serial import compute_fingerprint
from web.api.chroma_sync import sync_finding_to_chroma

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    import shutil

    real_config = Path(__file__).resolve().parents[3] / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _seed_finding(finding_repo: object, run_id: int, row: dict) -> int:
    finding_repo.upsert_findings(run_id, [row])  # type: ignore[union-attr]
    fp = compute_fingerprint(row)
    ids = finding_repo.get_ids_by_fingerprints([fp])  # type: ignore[union-attr]
    return ids[0]


def _make_rag_engine(base_path: str, project_name: str) -> RAGEngine:
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        return RAGEngine(project_name=project_name, base_path=base_path)


@pytest.fixture()
def phase5_env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    base_path = str(tmp_path)
    project_name = "test-proj"

    run_repo, finding_repo, _, _ = make_store(base_path, project_name)
    run_id = run_repo.create_run({})

    semgrep_row = {
        "tool": "semgrep",
        "profile": "default",
        "file_path": "src/app.py",
        "rule_id": "python.flask.sqli",
        "severity": "high",
        "finding_type": json.dumps(["vulnerability"]),
        "meta": json.dumps({"profile": "default"}),
    }
    finding_id = _seed_finding(finding_repo, run_id, semgrep_row)

    engine = _make_rag_engine(base_path, project_name)

    return {
        "base_path": base_path,
        "project_name": project_name,
        "finding_id": finding_id,
        "finding_repo": finding_repo,
        "engine": engine,
    }


def _sync(env: dict, finding_id: int | None = None) -> None:
    fid = finding_id if finding_id is not None else env["finding_id"]
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        sync_finding_to_chroma(
            finding_id=fid,
            rag_engine=env["engine"],
            finding_repo=env["finding_repo"],
        )


class TestPhase5ChromaSync:
    def test_upsert_creates_doc_with_sqlite_id(self, phase5_env: dict) -> None:
        """sync_finding_to_chroma upserts a doc whose ID is str(findings.id)."""
        finding_id = phase5_env["finding_id"]
        _sync(phase5_env)

        doc = phase5_env["engine"].get_document_by_id(str(finding_id))
        assert doc is not None

    def test_doc_has_tool_and_profile_only(self, phase5_env: dict) -> None:
        """Upserted ChromaDB doc has exactly {tool, profile} metadata."""
        _sync(phase5_env)

        finding_id = phase5_env["finding_id"]
        doc = phase5_env["engine"].get_document_by_id(str(finding_id))
        assert doc is not None
        assert set(doc["metadata"].keys()) == {"tool", "profile"}
        assert doc["metadata"]["tool"] == "semgrep"
        assert doc["metadata"]["profile"] == "default"

    def test_sync_is_idempotent(self, phase5_env: dict) -> None:
        """Calling sync twice leaves exactly one doc in ChromaDB."""
        _sync(phase5_env)
        _sync(phase5_env)

        assert phase5_env["engine"].count_documents() == 1

    def test_noop_when_rag_engine_is_none(self, phase5_env: dict) -> None:
        """No exception when rag_engine is None."""
        sync_finding_to_chroma(
            finding_id=phase5_env["finding_id"],
            rag_engine=None,
            finding_repo=phase5_env["finding_repo"],
        )
        assert phase5_env["engine"].count_documents() == 0

    def test_noop_when_finding_not_found(self, phase5_env: dict) -> None:
        """No exception when finding_id does not exist in SQLite."""
        _sync(phase5_env, finding_id=99999)
        assert phase5_env["engine"].count_documents() == 0
