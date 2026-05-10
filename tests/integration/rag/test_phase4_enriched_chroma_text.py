"""Integration tests: enriched SQLite meta fields flow into ChromaDB text.

Verifies that fields stored in the meta blob (risk_type, remediation) are
merged into the row dict by deserialise_row() and then rendered into the
ChromaDB document text by SemgrepHandler.render().
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from application.pipeline.fingerprint import compute_fingerprint
from application.pipeline.strategies import PersistOnlyStrategy
from application.ports.embedding_provider import EmbeddingProvider
from application.rag.knowledge_base import FindingKnowledgeBase
from core.project_paths import ProjectPaths
from domain.pipeline.events import IngestCompleted
from infrastructure.store import make_store
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex

pytestmark = pytest.mark.integration

_PROJECT_NAME = "test-enriched-meta"
_DIM = 8


class _DeterministicEmbedding(EmbeddingProvider):
    def is_available(self) -> bool:
        return True

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return list(struct.unpack(f"<{_DIM}f", digest[: _DIM * 4]))


def _build_test_kb(project_name: str, base_path: Path) -> FindingKnowledgeBase:
    paths = ProjectPaths.from_canonical(base_path, project_name)
    paths.chroma_db.mkdir(parents=True, exist_ok=True)
    chat_provider: Any = object()
    vector_index = ChromaDBVectorIndex(
        chroma_path=paths.chroma_db,
        collection_name=f"findings_{project_name}",
        embedding_provider=_DeterministicEmbedding(),
    )
    return FindingKnowledgeBase(
        vector_index=vector_index,
        chat_provider=chat_provider,
        project_name=project_name,
        base_path=base_path,
    )


def _write_global_config(base_path: Path) -> None:
    real_config = Path(__file__).resolve().parents[3] / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _seed_finding(finding_repo: object, run_id: int, row: dict) -> int:
    finding_repo.insert_findings(run_id, [row])  # type: ignore[union-attr]
    fp = compute_fingerprint(row)
    ids = finding_repo.get_ids_by_fingerprints([fp])  # type: ignore[union-attr]
    return ids[0]


def _dispatch(env: dict, ids: list[int]) -> None:
    event = IngestCompleted(
        ids=ids,
        failed_tools=[],
        run_id=env["run_id"],
        project_name=env["project_name"],
        base_path=env["base_path"],
    )
    with patch(
        "application.pipeline.handlers._build_knowledge_base",
        side_effect=_build_test_kb,
    ):
        env["handler"].handle(event)


@pytest.fixture()
def env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    base_path = str(tmp_path)

    run_repo, finding_repo, _, _ = make_store(base_path, _PROJECT_NAME)
    run_id = run_repo.create_run({})

    handler = PersistOnlyStrategy(finding_repo=finding_repo)

    return {
        "base_path": base_path,
        "project_name": _PROJECT_NAME,
        "run_id": run_id,
        "finding_repo": finding_repo,
        "handler": handler,
    }


class TestEnrichedChromaText:
    def test_enriched_semgrep_meta_appears_in_chroma_text(self, env: dict) -> None:
        """risk_type and remediation from meta blob appear in ChromaDB text."""
        row = {
            "tool": "semgrep",
            "profile": "default",
            "rule_id": "python.django.injection",
            "file_path": "app/views.py",
            "line_start": 12,
            "severity": "high",
            "finding_type": json.dumps(["vulnerability"]),
            "risk_type": "injection",
            "remediation": "sanitize inputs",
        }
        finding_id = _seed_finding(env["finding_repo"], env["run_id"], row)

        _dispatch(env, [finding_id])

        kb = _build_test_kb(env["project_name"], Path(env["base_path"]))
        try:
            doc = kb.get_finding(str(finding_id))
            assert doc is not None, "ChromaDB document was not written"
            text = doc["document"]
            assert text is not None
            assert "injection" in text, (
                f"Expected 'injection' (risk_type) in document text; got: {text!r}"
            )
            assert "sanitize inputs" in text, (
                f"Expected 'sanitize inputs' (remediation) in document text; "
                f"got: {text!r}"
            )
            assert doc["metadata"] is not None
            assert doc["metadata"]["tool"] == "semgrep"
        finally:
            kb.close()

    def test_unenriched_semgrep_still_written_to_chroma(self, env: dict) -> None:
        """A semgrep finding without enrichment fields is still written to ChromaDB."""
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

        kb = _build_test_kb(env["project_name"], Path(env["base_path"]))
        try:
            doc = kb.get_finding(str(finding_id))
            assert doc is not None, "ChromaDB document was not written"
            assert doc["metadata"] is not None
            assert doc["metadata"]["tool"] == "semgrep"
        finally:
            kb.close()
