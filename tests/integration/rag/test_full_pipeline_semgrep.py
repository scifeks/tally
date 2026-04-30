"""Integration test: full semgrep pipeline end-to-end.

Exercises IngestHandler → EnrichmentHandler (LLM mocked) →
ChromaDBHandler → RAG query against a real SQLite database and a
real ChromaDB instance.  No external network services are used.
"""

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

from application.pipeline.factory import PipelineFactory  # noqa: E402
from application.project import ProjectManager  # noqa: E402
from application.rag.engine import RAGEngine  # noqa: E402
from application.rag.enrichment import EnrichmentPipeline  # noqa: E402
from domain.pipeline.events import ToolCompleted  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.store import make_store  # noqa: E402

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSemgrepFullPipeline:
    def test_semgrep_full_pipeline_ingest_enrich_query(self, tmp_path: Path) -> None:
        """Full pipeline: ToolCompleted → SQLite → LLM enrich → ChromaDB → query.

        Steps verified:
        1. IngestHandler normalizes and writes 1 semgrep finding to SQLite.
        2. EnrichmentHandler calls the (mocked) LLM and writes risk_type to
           the finding's metadata; enriched flag becomes 1.
        3. ChromaDBHandler upserts the enriched row into ChromaDB.
        4. RAGEngine.query_collection() returns ≥1 result whose tool
           metadata equals "semgrep".
        """
        project_name = "test-semgrep-pipeline"
        _write_global_config(tmp_path)

        # Set up project directories so ConfigManager.load_repositories works
        pm = ProjectManager(base_path=str(tmp_path))
        pm.create_project_dirs(project_name)
        pm.save_project(project_name)

        # Create SQLite store and a run to attach findings to
        run_repo, finding_repo, _, _ = make_store(str(tmp_path), project_name)
        run_id = run_repo.create_run({})

        # Wire the event bus
        bus = PipelineFactory.create()

        # Build event
        result = _make_semgrep_result()
        event = ToolCompleted(
            result=result,
            profile="default",
            run_id=run_id,
            project_name=project_name,
            base_path=str(tmp_path),
        )

        default_fn = ef.DefaultEmbeddingFunction()
        with (
            patch.object(
                EnrichmentPipeline,
                "_call_per_field",
                return_value={"risk_type": "sql_injection"},
            ),
            patch.object(
                RAGEngine,
                "_build_embedding_function",
                return_value=default_fn,
            ),
        ):
            bus.dispatch(event)

        # ------------------------------------------------------------------
        # Assert SQLite state
        # ------------------------------------------------------------------
        findings = finding_repo.get_all_findings()
        assert len(findings) == 1, f"expected 1 finding in SQLite, got {len(findings)}"
        row = findings[0]
        assert row["enriched"] == 1, "finding must be marked enriched=1"
        meta = json.loads(row["meta"] or "{}")
        assert meta.get("risk_type") == "sql_injection", (
            f"risk_type not written to meta: {meta}"
        )

        # ------------------------------------------------------------------
        # Assert ChromaDB state via a fresh query engine
        # ------------------------------------------------------------------
        with patch.object(
            RAGEngine, "_build_embedding_function", return_value=default_fn
        ):
            query_engine = RAGEngine(project_name=project_name, base_path=str(tmp_path))

        results = query_engine.query_collection(
            query_texts=["sql injection"], n_results=5
        )

        docs = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        assert len(docs) >= 1, "ChromaDB returned no documents"
        assert metadatas[0]["tool"] == "semgrep", (
            f"expected tool=semgrep in metadata, got: {metadatas[0]}"
        )
