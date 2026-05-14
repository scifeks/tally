"""Integration tests: FindingsService patch upserts into ChromaDB by sqlite id."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

from application.findings.analyst_service import FindingAnalystService
from application.findings.findings_service import FindingsService
from application.locking import LockQueryService
from application.ports.embedding_provider import EmbeddingProvider
from application.ports.finding_event_sink import NullFindingEventSink
from application.rag.knowledge_base import FindingKnowledgeBase
from core.project_paths import ProjectPaths
from infrastructure.store import make_store
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex
from tests.finding_helpers import normalize_test_findings

pytestmark = pytest.mark.integration


_DIM = 8


class _DeterministicEmbedding(EmbeddingProvider):
    def is_available(self) -> bool:
        return True

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return list(struct.unpack(f"<{_DIM}f", digest[: _DIM * 4]))


def _seed_finding(finding_repo: object, run_id: int, row: dict) -> int:
    normalized = normalize_test_findings([row])
    finding_repo.insert_findings(  # type: ignore[union-attr]
        run_id, normalized
    )
    ids = finding_repo.get_ids_by_fingerprints([normalized[0].fingerprint])  # type: ignore[union-attr]
    return ids[0]


def _make_kb(base_path: Path, project_name: str) -> FindingKnowledgeBase:
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


def _build_service(
    *,
    finding_repo: Any,
    history_repo: Any,
    project_repo: Any,
    project_name: str,
    base_path: Path,
    kb: FindingKnowledgeBase | None,
) -> FindingsService:
    return FindingsService(
        finding_repo=finding_repo,
        history_repo=history_repo,
        project_repo=project_repo,
        analyst=FindingAnalystService(finding_repo),
        lock_query=LockQueryService(),
        project_id=1,
        project_name=project_name,
        findings_db_exists=True,
        knowledge_base_cache={project_name: kb},
        base_path=str(base_path),
        event_sink=NullFindingEventSink(),
    )


@pytest.fixture()
def phase5_env(tmp_path: Path) -> dict:
    base_path = tmp_path
    project_name = "test-proj"

    paths = ProjectPaths.from_canonical(base_path, project_name)
    paths.root.mkdir(parents=True, exist_ok=True)

    run_repo, finding_repo, history_repo, project_repo = make_store(
        str(base_path), project_name
    )
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

    kb = _make_kb(base_path, project_name)

    return {
        "base_path": base_path,
        "project_name": project_name,
        "finding_id": finding_id,
        "finding_repo": finding_repo,
        "history_repo": history_repo,
        "project_repo": project_repo,
        "kb": kb,
    }


def _service_with_kb(env: dict, kb: FindingKnowledgeBase | None) -> FindingsService:
    return _build_service(
        finding_repo=env["finding_repo"],
        history_repo=env["history_repo"],
        project_repo=env["project_repo"],
        project_name=env["project_name"],
        base_path=env["base_path"],
        kb=kb,
    )


def _patch(env: dict, finding_id: int | None = None) -> None:
    fid = finding_id if finding_id is not None else env["finding_id"]
    service = _service_with_kb(env, env["kb"])
    service.patch_finding(fid, {"description": "updated by analyst"})


class TestPhase5ChromaSync:
    def test_upsert_creates_doc_with_sqlite_id(self, phase5_env: dict) -> None:
        finding_id = phase5_env["finding_id"]
        _patch(phase5_env)

        doc = phase5_env["kb"].get_finding(str(finding_id))
        assert doc is not None

    def test_doc_has_tool_and_profile_only(self, phase5_env: dict) -> None:
        _patch(phase5_env)

        finding_id = phase5_env["finding_id"]
        doc = phase5_env["kb"].get_finding(str(finding_id))
        assert doc is not None
        assert set(doc["metadata"].keys()) == {"tool", "profile"}
        assert doc["metadata"]["tool"] == "semgrep"
        assert doc["metadata"]["profile"] == "default"

    def test_sync_is_idempotent(self, phase5_env: dict) -> None:
        _patch(phase5_env)
        _patch(phase5_env)

        assert phase5_env["kb"].count() == 1

    def test_noop_when_kb_is_none(self, phase5_env: dict) -> None:
        service = _service_with_kb(phase5_env, kb=None)
        service.patch_finding(
            phase5_env["finding_id"], {"description": "no kb available"}
        )
        assert phase5_env["kb"].count() == 0

    def test_noop_when_finding_not_found(self, phase5_env: dict) -> None:
        # update_fields short-circuits to False for a non-existent id, so
        # patch_finding returns None and never reaches _sync_to_chroma.
        service = _service_with_kb(phase5_env, phase5_env["kb"])
        result = service.patch_finding(99999, {"description": "ghost"})
        assert result is None
        assert phase5_env["kb"].count() == 0
