"""Phase 4 integration tests: ChromaDBHandler writes enriched rows to ChromaDB."""

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


@pytest.fixture()
def phase4_env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    base_path = str(tmp_path)
    project_name = "test-proj"

    run_repo, finding_repo, _, _ = make_store(base_path, project_name)
    run_id = run_repo.create_run({})

    semgrep_row = {
        "tool": "semgrep",
        "profile": "default",
        "rule_id": "python.django.security.sql-injection",
        "file_path": "src/api/users.py",
        "line_start": 42,
        "line_end": 42,
        "severity": "high",
        "finding_type": json.dumps(["vulnerability"]),
        "description": "SQL injection via unsanitized user input",
    }
    semgrep_id = _seed_finding(finding_repo, run_id, semgrep_row)

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

    handler = PersistOnlyStrategy()

    return {
        "base_path": base_path,
        "project_name": project_name,
        "run_id": run_id,
        "semgrep_id": semgrep_id,
        "gitleaks_id": gitleaks_id,
        "handler": handler,
    }


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


def _open_kb(env: dict) -> FindingKnowledgeBase:
    return _build_test_kb(env["project_name"], Path(env["base_path"]))


class TestPhase4ChromaDBWrite:
    def test_noop_when_ids_empty(self, phase4_env: dict) -> None:
        """handle() with empty ids list does nothing."""
        _dispatch(phase4_env, ids=[])
        kb = _open_kb(phase4_env)
        try:
            assert kb.count() == 0
        finally:
            kb.close()

    def test_chromadb_docs_have_tool_and_profile_metadata(
        self, phase4_env: dict
    ) -> None:
        """ChromaDB docs contain exactly {tool, profile} metadata."""
        _dispatch(phase4_env, ids=[phase4_env["semgrep_id"], phase4_env["gitleaks_id"]])

        kb = _open_kb(phase4_env)
        try:
            results = kb.find_by_filter(filter=None, limit=10, offset=0)
            assert len(results) == 2
            for r in results:
                meta = r["metadata"]
                assert meta is not None
                assert set(meta.keys()) == {"tool", "profile"}
                assert meta["profile"] == "default"
            tools = {r["metadata"]["tool"] for r in results if r["metadata"]}
            assert tools == {"semgrep", "gitleaks"}
        finally:
            kb.close()

    def test_chromadb_doc_ids_are_sqlite_primary_keys(self, phase4_env: dict) -> None:
        """ChromaDB doc IDs equal str(findings.id)."""
        semgrep_id = phase4_env["semgrep_id"]
        gitleaks_id = phase4_env["gitleaks_id"]
        _dispatch(phase4_env, ids=[semgrep_id, gitleaks_id])

        kb = _open_kb(phase4_env)
        try:
            assert kb.get_finding(str(semgrep_id)) is not None
            assert kb.get_finding(str(gitleaks_id)) is not None
        finally:
            kb.close()

    def test_chromadb_doc_text_is_rendered(self, phase4_env: dict) -> None:
        """ChromaDB document text comes from ToolHandler.render()."""
        semgrep_id = phase4_env["semgrep_id"]
        _dispatch(phase4_env, ids=[semgrep_id])

        kb = _open_kb(phase4_env)
        try:
            doc = kb.get_finding(str(semgrep_id))
            assert doc is not None
            text = doc["document"]
            assert text is not None
            assert "[semgrep]" in text
            assert "src/api/users.py" in text
            assert "Repository: " in text
        finally:
            kb.close()

    def test_delete_then_add_on_rerun(self, phase4_env: dict) -> None:
        """Second dispatch replaces existing ChromaDB docs for the same tool/profile."""
        semgrep_id = phase4_env["semgrep_id"]

        _dispatch(phase4_env, ids=[semgrep_id])
        kb = _open_kb(phase4_env)
        try:
            assert kb.count() == 1
        finally:
            kb.close()

        _dispatch(phase4_env, ids=[semgrep_id])
        kb = _open_kb(phase4_env)
        try:
            assert kb.count() == 1
        finally:
            kb.close()

    def test_only_requested_ids_are_written(self, phase4_env: dict) -> None:
        """Only the IDs in event.ids are written; others remain absent."""
        semgrep_id = phase4_env["semgrep_id"]
        gitleaks_id = phase4_env["gitleaks_id"]

        _dispatch(phase4_env, ids=[semgrep_id])

        kb = _open_kb(phase4_env)
        try:
            assert kb.get_finding(str(semgrep_id)) is not None
            assert kb.get_finding(str(gitleaks_id)) is None
        finally:
            kb.close()

    def test_orphan_removal_on_rescan_with_fewer_findings(
        self, phase4_env: dict
    ) -> None:
        """Second scan with fewer findings leaves no orphaned ChromaDB docs.

        First scan produces 3 semgrep findings -> 3 docs in ChromaDB.
        Second scan produces 1 semgrep finding -> exactly 1 doc remains.
        """
        base_path = phase4_env["base_path"]
        project_name = phase4_env["project_name"]
        _, finding_repo, _, _ = make_store(base_path, project_name)
        run_id = phase4_env["run_id"]

        extra_rows = [
            {
                "tool": "semgrep",
                "profile": "default",
                "rule_id": "python.django.security.sql-injection",
                "file_path": f"src/api/endpoint{i}.py",
                "line_start": 10 * i,
                "line_end": 10 * i,
                "severity": "high",
                "finding_type": json.dumps(["vulnerability"]),
            }
            for i in (2, 3)
        ]
        extra_ids = [_seed_finding(finding_repo, run_id, r) for r in extra_rows]
        first_scan_ids = [phase4_env["semgrep_id"]] + extra_ids

        _dispatch(phase4_env, ids=first_scan_ids)
        kb = _open_kb(phase4_env)
        try:
            assert kb.count() == 3, "expected 3 ChromaDB docs after first scan"
        finally:
            kb.close()

        new_row = {
            "tool": "semgrep",
            "profile": "default",
            "rule_id": "python.flask.security.xss",
            "file_path": "src/views/index.py",
            "line_start": 99,
            "line_end": 99,
            "severity": "medium",
            "finding_type": json.dumps(["vulnerability"]),
        }
        new_id = _seed_finding(finding_repo, run_id, new_row)

        _dispatch(phase4_env, ids=[new_id])
        kb = _open_kb(phase4_env)
        try:
            assert kb.count() == 1, "orphaned docs from first scan were not deleted"
        finally:
            kb.close()
