"""Integration tests for the ZAP → ChromaDB ingestion pipeline.

Run from the tally project root:
    pytest tests/ingest/test_zap.py -v
"""

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
from core.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402

_OLLAMA_URL = "http://localhost:11434"
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zap_result(parsed_data: dict, output_files: dict | None = None) -> ToolResult:
    return ToolResult(
        tool_name="zap",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=RAGEngine.now_iso(),
        duration_seconds=0.1,
    )


def _write_global_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "chat_llm_provider": "ollama",
                "enrichment_llm_provider": "ollama",
                "report_llm_provider": "ollama",
                "embedding_provider": "ollama_embedding",
                "ollama": {
                    "base_url": _OLLAMA_URL,
                    "model": "qwen3:14b",
                },
                "ollama_embedding": {"model": "nomic-embed-text:latest"},
            }
        )
    )


def _write_commands_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "zap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/zap",
                },
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/gitleaks",
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


def _get_all_docs(engine: RAGEngine) -> dict[str, list]:
    assert engine._collection is not None
    result = engine._collection.get(include=["documents", "metadatas"])
    return {
        "ids": result["ids"],
        "documents": list(result["documents"] or []),
        "metadatas": list(result["metadatas"] or []),
    }


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


@pytest.fixture()
def alerts_parsed_data() -> dict:
    raw = json.loads((_FIXTURES / "zap_alerts.json").read_text())
    alerts = []
    for a in raw["alerts"]:
        entry: dict = {
            "alert_name": a["alert_name"],
            "risk": a["risk"],
            "confidence": a["confidence"],
            "description": a["description"],
            "solution": a["solution"],
            "url": a["url"],
            "method": a["method"],
            "param": a.get("param"),
            "evidence": a.get("evidence"),
            "cwe_id": a.get("cwe_id"),
        }
        alerts.append(entry)
    return {"alerts": alerts, "summary": raw["summary"]}


# ---------------------------------------------------------------------------
# Ingestor tests
# ---------------------------------------------------------------------------


class TestZapIngestor:
    def test_chunk_count(self, project_env: dict, alerts_parsed_data: dict) -> None:
        """2 alerts in fixture → 2 documents ingested."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert len(doc_ids) == 2
        assert engine.count_documents() == 2

    def test_shared_metadata(self, project_env: dict, alerts_parsed_data: dict) -> None:
        """ZAP chunks have domain='web', type_vulnerability=True."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert meta["domain"] == "web"
            assert meta["enriched"] is False
            assert meta["type_vulnerability"] is True
            assert meta["type_secret"] is False
            assert meta["type_weakness"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_exposure"] is False
            assert meta["type_dependency"] is False

    def test_metadata_fidelity(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """Metadata fields match the fixture alert data."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        assert len(all_docs["metadatas"]) == 2
        by_name = {m["alert_name"]: m for m in all_docs["metadatas"]}
        sql_meta = by_name["SQL Injection"]
        assert sql_meta["tool"] == "zap"
        assert sql_meta["profile"] == "test-repo"
        assert sql_meta["finding_type"] == '["vulnerability"]'
        assert sql_meta["severity"] == "high"
        assert sql_meta["confidence"] == "probable"
        assert sql_meta["url"] == "https://example.com/api/users"

    def test_remediation_promoted(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """'remediation' key is present and non-empty for all docs."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert "remediation" in meta, f"'remediation' missing from {meta}"
            assert meta["remediation"], "remediation must not be empty"

    def test_description_promoted(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """'description' key is present and non-empty for all docs."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert "description" in meta, f"'description' missing from {meta}"
            assert meta["description"], "description must not be empty"

    def test_method_uppercase(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """method field is uppercased in metadata."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        by_name = {m["alert_name"]: m for m in all_docs["metadatas"]}
        assert by_name["SQL Injection"]["method"] == "POST"
        assert by_name["X-Content-Type-Options Header Missing"]["method"] == "GET"

    def test_optional_param_present(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """First alert (SQL Injection) has 'param' in metadata."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        sql_metas = [
            m for m in all_docs["metadatas"] if m["alert_name"] == "SQL Injection"
        ]
        assert len(sql_metas) == 1
        assert "param" in sql_metas[0]
        assert sql_metas[0]["param"] == "id"

    def test_optional_param_absent(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """Second alert (header missing) has no 'param' key in metadata."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        header_metas = [
            m
            for m in all_docs["metadatas"]
            if m["alert_name"] == "X-Content-Type-Options Header Missing"
        ]
        assert len(header_metas) == 1
        assert "param" not in header_metas[0]

    def test_optional_cwe_id_present(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """First alert has cwe_id as int in metadata."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        sql_metas = [
            m for m in all_docs["metadatas"] if m["alert_name"] == "SQL Injection"
        ]
        assert len(sql_metas) == 1
        assert "cwe_id" in sql_metas[0]
        assert isinstance(sql_metas[0]["cwe_id"], int)
        assert sql_metas[0]["cwe_id"] == 89

    def test_optional_cwe_id_absent(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """Second alert (null cwe_id) has no 'cwe_id' key in metadata."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        header_metas = [
            m
            for m in all_docs["metadatas"]
            if m["alert_name"] == "X-Content-Type-Options Header Missing"
        ]
        assert len(header_metas) == 1
        assert "cwe_id" not in header_metas[0]

    def test_no_none_or_empty_metadata_values(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """No metadata value is None or empty string."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            for key, val in meta.items():
                assert val is not None, f"None value for key {key!r}"
                if key != "source_file":
                    assert val != "", f"Empty string for key {key!r}"

    def test_return_type_is_list(
        self, project_env: dict, alerts_parsed_data: dict
    ) -> None:
        """ingest_tool_output returns list[str] with correct length."""
        result = _make_zap_result(alerts_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == 2
        assert all(isinstance(i, str) for i in doc_ids)
