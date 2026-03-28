"""Integration tests: enriched SQLite meta fields flow into ChromaDB text.

Verifies that fields stored in the meta blob (risk_type, remediation) are
merged into the row dict by deserialise_row() and then rendered into the
ChromaDB document text by SemgrepHandler.render().
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

from application.pipeline.handlers import ChromaDBHandler
from application.rag.engine import RAGEngine
from domain.pipeline.events import EnrichmentCompleted
from domain.pipeline.fingerprint import compute_fingerprint
from infrastructure.store import make_store

pytestmark = pytest.mark.integration

_PROJECT_NAME = "test-enriched-meta"


def _write_global_config(base_path: Path) -> None:
    import shutil

    real_config = Path(__file__).resolve().parents[3] / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _make_rag_engine(base_path: str, project_name: str) -> RAGEngine:
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        return RAGEngine(project_name=project_name, base_path=base_path)


def _seed_finding(finding_repo: object, run_id: int, row: dict) -> int:
    finding_repo.upsert_findings(run_id, [row])  # type: ignore[union-attr]
    fp = compute_fingerprint(row)
    ids = finding_repo.get_ids_by_fingerprints([fp])  # type: ignore[union-attr]
    return ids[0]


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


@pytest.fixture()
def env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    base_path = str(tmp_path)

    run_repo, finding_repo, _, _ = make_store(base_path, _PROJECT_NAME)
    run_id = run_repo.create_run({})

    engine = _make_rag_engine(base_path, _PROJECT_NAME)
    handler = ChromaDBHandler()

    return {
        "base_path": base_path,
        "project_name": _PROJECT_NAME,
        "run_id": run_id,
        "finding_repo": finding_repo,
        "engine": engine,
        "handler": handler,
    }


class TestEnrichedChromaText:
    def test_enriched_semgrep_meta_appears_in_chroma_text(self, env: dict) -> None:
        """risk_type and remediation from meta blob appear in ChromaDB text.

        upsert_findings() stores unknown fields (not in _DIRECT_COLUMNS) in the
        meta blob.  get_by_ids() / deserialise_row() merges the blob back into
        the row dict at the top level.  SemgrepHandler.render() then writes
        risk_type and remediation into the ChromaDB document text.
        """
        row = {
            "tool": "semgrep",
            "profile": "default",
            "rule_id": "python.django.injection",
            "file_path": "app/views.py",
            "line_start": 12,
            "severity": "high",
            "finding_type": json.dumps(["vulnerability"]),
            # These unknown keys are stored in the meta blob by upsert_findings
            "risk_type": "injection",
            "remediation": "sanitize inputs",
        }
        finding_id = _seed_finding(env["finding_repo"], env["run_id"], row)

        _dispatch(env, [finding_id])

        doc = env["engine"].get_document_by_id(str(finding_id))
        assert doc is not None, "ChromaDB document was not written"
        text = doc["document"]
        assert "injection" in text, (
            f"Expected 'injection' (risk_type) in document text; got: {text!r}"
        )
        assert "sanitize inputs" in text, (
            f"Expected 'sanitize inputs' (remediation) in document text; got: {text!r}"
        )
        assert doc["metadata"]["tool"] == "semgrep"

    def test_unenriched_semgrep_still_written_to_chroma(self, env: dict) -> None:
        """A semgrep finding without enrichment fields is still written to ChromaDB.

        ChromaDBHandler does not require enriched=1; it writes every row
        returned by get_by_ids().  The document should be present with correct
        tool metadata even when no LLM enrichment has run.
        """
        row = {
            "tool": "semgrep",
            "profile": "default",
            "rule_id": "python.requests.no-auth",
            "file_path": "app/client.py",
            "line_start": 5,
            "severity": "medium",
            "finding_type": json.dumps(["vulnerability"]),
        }
        finding_id = _seed_finding(env["finding_repo"], env["run_id"], row)

        _dispatch(env, [finding_id])

        doc = env["engine"].get_document_by_id(str(finding_id))
        assert doc is not None, "ChromaDB document was not written"
        assert doc["metadata"]["tool"] == "semgrep"
