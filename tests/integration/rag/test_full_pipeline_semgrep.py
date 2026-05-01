"""Integration test: full semgrep pipeline end-to-end.

Exercises IngestHandler -> EnrichmentHandler (LLM mocked) ->
ChromaDBHandler -> RAG query against a real SQLite database and a
real ChromaDB instance. No external network services are used.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.pipeline.factory import PipelineFactory  # noqa: E402
from application.ports.embedding_provider import EmbeddingProvider  # noqa: E402
from application.project import ProjectManager  # noqa: E402
from application.rag.enrichment import EnrichmentPipeline  # noqa: E402
from application.rag.knowledge_base import FindingKnowledgeBase  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402
from domain.pipeline.events import ToolCompleted  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex  # noqa: E402

pytestmark = pytest.mark.integration


_DIM = 8


class _DeterministicEmbedding(EmbeddingProvider):
    def is_available(self) -> bool:
        return True

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return list(struct.unpack(f"<{_DIM}f", digest[: _DIM * 4]))


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _make_semgrep_result() -> ToolResult:
    return ToolResult(
        tool_name="semgrep",
        success=True,
        output="",
        parsed_data={
            "findings": [
                {
                    "rule_id": "sql-injection",
                    "severity": "high",
                    "message": "SQL injection in query parameter",
                    "file_path": "src/db.py",
                    "line_start": 42,
                    "line_end": 42,
                }
            ]
        },
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


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


class TestSemgrepFullPipeline:
    def test_semgrep_full_pipeline_ingest_enrich_query(self, tmp_path: Path) -> None:
        """Full pipeline: ToolCompleted -> SQLite -> LLM enrich -> ChromaDB -> query.

        Steps verified:
        1. IngestHandler normalizes and writes 1 semgrep finding to SQLite.
        2. EnrichmentHandler calls the (mocked) LLM and writes risk_type to
           the finding's metadata; enriched flag becomes 1.
        3. ChromaDBHandler upserts the enriched row into ChromaDB.
        4. KnowledgeBase.find_relevant() returns >=1 result whose tool
           metadata equals "semgrep".
        """
        project_name = "test-semgrep-pipeline"
        _write_global_config(tmp_path)

        pm = ProjectManager(base_path=str(tmp_path))
        pm.create_project_dirs(project_name)
        pm.save_project(project_name)

        run_repo, finding_repo, _, _ = make_store(str(tmp_path), project_name)
        run_id = run_repo.create_run({})

        bus = PipelineFactory.create()

        result = _make_semgrep_result()
        event = ToolCompleted(
            result=result,
            profile="default",
            run_id=run_id,
            project_name=project_name,
            base_path=str(tmp_path),
        )

        with (
            patch.object(
                EnrichmentPipeline,
                "_call_per_field",
                return_value={"risk_type": "sql_injection"},
            ),
            patch(
                "application.pipeline.handlers._build_knowledge_base",
                side_effect=_build_test_kb,
            ),
        ):
            bus.dispatch(event)

        findings = finding_repo.get_all_findings()
        assert len(findings) == 1, f"expected 1 finding in SQLite, got {len(findings)}"
        row = findings[0]
        assert row["enriched"] == 1, "finding must be marked enriched=1"
        meta = json.loads(row["meta"] or "{}")
        assert meta.get("risk_type") == "sql_injection", (
            f"risk_type not written to meta: {meta}"
        )

        kb = _build_test_kb(project_name, tmp_path)
        try:
            results = kb.find_relevant("sql injection", n_results=5)
        finally:
            kb.close()

        assert len(results) >= 1, "ChromaDB returned no documents"
        assert results[0]["metadata"] is not None
        assert results[0]["metadata"]["tool"] == "semgrep", (
            f"expected tool=semgrep in metadata, got: {results[0]['metadata']}"
        )
