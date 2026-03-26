"""Phase 4 integration tests: ChromaDBHandler writes enriched rows to ChromaDB."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

from application.pipeline.handlers import ChromaDBHandler
from application.rag.engine import RAGEngine
from domain.pipeline.events import EnrichmentCompleted
from infrastructure.store import make_store
from infrastructure.store.repositories.findings_serial import compute_fingerprint

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
def phase4_env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    base_path = str(tmp_path)
    project_name = "test-proj"

    run_repo, finding_repo, _, _ = make_store(base_path, project_name)
    run_id = run_repo.create_run({})

    nmap_row = {
        "tool": "nmap",
        "profile": "default",
        "ip_address": "10.0.0.1",
        "port": 80,
        "severity": "info",
        "finding_type": json.dumps(["exposure"]),
        "meta": json.dumps({"service": "http"}),
    }
    nmap_id = _seed_finding(finding_repo, run_id, nmap_row)

    gitleaks_row = {
        "tool": "gitleaks",
        "profile": "default",
        "rule_id": "aws-key",
        "file": "src/config.py",
        "severity": "high",
        "finding_type": json.dumps(["secret"]),
        "meta": json.dumps({"line_number": 42}),
    }
    gitleaks_id = _seed_finding(finding_repo, run_id, gitleaks_row)

    engine = _make_rag_engine(base_path, project_name)
    handler = ChromaDBHandler()

    return {
        "base_path": base_path,
        "project_name": project_name,
        "run_id": run_id,
        "nmap_id": nmap_id,
        "gitleaks_id": gitleaks_id,
        "engine": engine,
        "handler": handler,
    }


def _dispatch(env: dict, ids: list[int]) -> None:
    event = EnrichmentCompleted(
        ids=ids,
        partial_success=False,
        run_id=env["run_id"],
        project_name=env["project_name"],
        base_path=env["base_path"],
    )
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        env["handler"].handle(event)


class TestPhase4ChromaDBWrite:
    def test_noop_when_ids_empty(self, phase4_env: dict) -> None:
        """handle() with empty ids list does nothing."""
        _dispatch(phase4_env, ids=[])
        assert phase4_env["engine"].count_documents() == 0

    def test_chromadb_docs_have_tool_and_profile_metadata(
        self, phase4_env: dict
    ) -> None:
        """ChromaDB docs contain exactly {tool, profile} metadata."""
        _dispatch(phase4_env, ids=[phase4_env["nmap_id"], phase4_env["gitleaks_id"]])

        all_meta = phase4_env["engine"].get_all_metadatas()
        assert len(all_meta) == 2
        for meta in all_meta:
            assert set(meta.keys()) == {"tool", "profile"}
            assert meta["profile"] == "default"
        tools = {m["tool"] for m in all_meta}
        assert tools == {"nmap", "gitleaks"}

    def test_chromadb_doc_ids_are_sqlite_primary_keys(self, phase4_env: dict) -> None:
        """ChromaDB doc IDs equal str(findings.id)."""
        nmap_id = phase4_env["nmap_id"]
        gitleaks_id = phase4_env["gitleaks_id"]
        _dispatch(phase4_env, ids=[nmap_id, gitleaks_id])

        engine = phase4_env["engine"]
        assert engine.get_document_by_id(str(nmap_id)) is not None
        assert engine.get_document_by_id(str(gitleaks_id)) is not None

    def test_chromadb_doc_text_is_rendered(self, phase4_env: dict) -> None:
        """ChromaDB document text comes from ToolHandler.render()."""
        nmap_id = phase4_env["nmap_id"]
        _dispatch(phase4_env, ids=[nmap_id])

        doc = phase4_env["engine"].get_document_by_id(str(nmap_id))
        assert doc is not None
        assert "[nmap]" in doc["document"]
        assert "10.0.0.1" in doc["document"]

    def test_delete_then_add_on_rerun(self, phase4_env: dict) -> None:
        """Second dispatch replaces existing ChromaDB docs for the same tool/profile."""
        nmap_id = phase4_env["nmap_id"]

        _dispatch(phase4_env, ids=[nmap_id])
        assert phase4_env["engine"].count_documents() == 1

        _dispatch(phase4_env, ids=[nmap_id])
        assert phase4_env["engine"].count_documents() == 1

    def test_only_requested_ids_are_written(self, phase4_env: dict) -> None:
        """Only the IDs in event.ids are written; others remain absent."""
        nmap_id = phase4_env["nmap_id"]
        gitleaks_id = phase4_env["gitleaks_id"]

        _dispatch(phase4_env, ids=[nmap_id])

        engine = phase4_env["engine"]
        assert engine.get_document_by_id(str(nmap_id)) is not None
        assert engine.get_document_by_id(str(gitleaks_id)) is None

    def test_orphan_removal_on_rescan_with_fewer_findings(
        self, phase4_env: dict
    ) -> None:
        """Second scan with fewer findings leaves no orphaned ChromaDB docs.

        First scan produces 3 nmap findings → 3 docs in ChromaDB.
        Second scan produces 1 nmap finding → exactly 1 doc remains.
        The 2 docs from the first scan must be deleted, not left behind.
        """
        base_path = phase4_env["base_path"]
        project_name = phase4_env["project_name"]
        run_repo, finding_repo, _, _ = make_store(base_path, project_name)
        run_id = phase4_env["run_id"]

        # Seed 2 more nmap rows (different ports) to simulate a 3-finding scan
        extra_rows = [
            {
                "tool": "nmap",
                "profile": "default",
                "ip_address": "10.0.0.1",
                "port": port,
                "severity": "informational",
                "finding_type": json.dumps(["exposure"]),
            }
            for port in (443, 8080)
        ]
        extra_ids = [_seed_finding(finding_repo, run_id, r) for r in extra_rows]
        first_scan_ids = [phase4_env["nmap_id"]] + extra_ids

        # First scan: 3 nmap findings
        _dispatch(phase4_env, ids=first_scan_ids)
        assert phase4_env["engine"].count_documents() == 3, (
            "expected 3 ChromaDB docs after first scan"
        )

        # Seed 1 new nmap finding (different port) to simulate rescan result
        new_row = {
            "tool": "nmap",
            "profile": "default",
            "ip_address": "10.0.0.2",
            "port": 22,
            "severity": "informational",
            "finding_type": json.dumps(["exposure"]),
        }
        new_id = _seed_finding(finding_repo, run_id, new_row)

        # Second scan: only 1 nmap finding
        _dispatch(phase4_env, ids=[new_id])
        assert phase4_env["engine"].count_documents() == 1, (
            "orphaned docs from first scan were not deleted"
        )
