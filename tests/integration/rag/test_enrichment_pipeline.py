"""Integration tests for EnrichmentPipeline (real ChromaDB)."""

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

from application.project import ProjectManager  # noqa: E402
from application.rag import EnrichmentPipeline, RAGEngine  # noqa: E402

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


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
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/gitleaks",
                },
                "zap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/zap",
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


def _make_llm_response(fields: list[str]) -> dict:
    values = {
        "risk_type": "exposed_service",
        "remediation": "Restrict access to this port via firewall rules.",
        "severity": "potential",
        "description": (
            "An open port was found exposing a potentially exploitable service."
        ),
    }
    return {f: values[f] for f in fields if f in values}


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


@pytest.fixture()
def seeded_engine(project_env: dict) -> RAGEngine:
    engine = _make_rag_engine(project_env)
    engine.add_documents(
        texts=["Leaked AWS access key found in config.py"],
        metadatas=[
            {
                "tool": "gitleaks",
                "enriched": False,
                "severity": "high",
                "confidence": "confirmed",
            }
        ],
        ids=["gl-001"],
    )
    engine.add_documents(
        texts=["Reflected XSS found in search parameter"],
        metadatas=[
            {
                "tool": "zap",
                "enriched": False,
                "severity": "high",
                "remediation": "Encode output.",
                "description": "XSS via search param.",
            }
        ],
        ids=["zap-001"],
    )
    engine.add_documents(
        texts=["Port 22 SSH open on 10.0.0.1"],
        metadatas={"tool": "nmap", "enriched": True, "risk_type": "exposed_service"},  # type: ignore[arg-type]
        ids=["nm-001"],
    )
    return engine


@pytest.fixture()
def pipeline(seeded_engine: RAGEngine) -> EnrichmentPipeline:
    return EnrichmentPipeline(seeded_engine, console=None)


class TestEnrichmentPipeline:
    def test_empty_ids_no_llm_call(self, pipeline: EnrichmentPipeline) -> None:
        with patch.object(pipeline, "_call_llm") as mock_llm:
            pipeline.enrich([])
            mock_llm.assert_not_called()

    def test_already_enriched_skipped(self, pipeline: EnrichmentPipeline) -> None:
        with patch.object(pipeline, "_call_llm") as mock_llm:
            pipeline.enrich(["nm-001"])
            mock_llm.assert_not_called()

    def test_all_tool_provided_no_llm_call(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["SQL injection in login form"],
            metadatas=[
                {
                    "tool": "zap",
                    "enriched": False,
                    "risk_type": "sql_injection",
                    "severity": "high",
                    "confidence": "probable",
                    "remediation": "Use parameterized queries.",
                    "description": "SQL injection found in login form.",
                    "owasp_name": "Injection",
                }
            ],
            ids=["zap-full-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich(["zap-full-001"])
            mock_llm.assert_not_called()

    def test_missing_fields_calls_llm_once(self, pipeline: EnrichmentPipeline) -> None:
        with patch.object(
            pipeline,
            "_call_llm",
            return_value=_make_llm_response(["risk_type"]),
        ) as mock_llm:
            pipeline.enrich(["zap-001"])
            mock_llm.assert_called_once()

    def test_enriched_true_after_success(
        self, pipeline: EnrichmentPipeline, seeded_engine: RAGEngine
    ) -> None:
        fields = ["risk_type", "remediation", "description"]
        with patch.object(
            pipeline, "_call_llm", return_value=_make_llm_response(fields)
        ):
            pipeline.enrich(["gl-001"])
        doc = seeded_engine.get_document_by_id("gl-001")
        assert doc is not None
        assert doc["metadata"]["enriched"] is True

    def test_enriched_fields_written_to_metadata(
        self, pipeline: EnrichmentPipeline, seeded_engine: RAGEngine
    ) -> None:
        fields = ["risk_type"]
        llm_response = _make_llm_response(fields)
        with patch.object(pipeline, "_call_llm", return_value=llm_response):
            pipeline.enrich(["zap-001"])
        doc = seeded_engine.get_document_by_id("zap-001")
        assert doc is not None
        for field in fields:
            assert field in doc["metadata"]
            assert doc["metadata"][field] == llm_response[field]

    def test_invalid_json_leaves_enriched_false(
        self, pipeline: EnrichmentPipeline, seeded_engine: RAGEngine
    ) -> None:
        with patch.object(
            pipeline,
            "_call_llm",
            side_effect=json.JSONDecodeError("err", "", 0),
        ):
            pipeline.enrich(["zap-001"])
        doc = seeded_engine.get_document_by_id("zap-001")
        assert doc is not None
        assert not doc["metadata"].get("enriched")

    def test_pipeline_continues_after_one_failure(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["Finding A"],
            metadatas=[{"tool": "semgrep", "enriched": False, "severity": "medium"}],
            ids=["cont-001"],
        )
        engine.add_documents(
            texts=["Finding B"],
            metadatas=[{"tool": "semgrep", "enriched": False, "severity": "medium"}],
            ids=["cont-002"],
        )
        p = EnrichmentPipeline(engine, console=None)

        def side_effect(doc_text, metadata, fields):
            if doc_text == "Finding A":
                raise json.JSONDecodeError("bad", "", 0)
            return _make_llm_response(["risk_type", "remediation", "description"])

        with patch.object(p, "_call_llm", side_effect=side_effect):
            p.enrich(["cont-001", "cont-002"])

        doc2 = engine.get_document_by_id("cont-002")
        assert doc2 is not None
        assert doc2["metadata"].get("enriched") is True

    def test_idempotent_second_run_skips(self, pipeline: EnrichmentPipeline) -> None:
        fields = ["risk_type"]
        with patch.object(
            pipeline, "_call_llm", return_value=_make_llm_response(fields)
        ) as mock_llm:
            pipeline.enrich(["zap-001"])
            pipeline.enrich(["zap-001"])
            assert mock_llm.call_count == 1

    def test_zap_skips_remediation_severity_description(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "zap"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == ["risk_type", "owasp_name"]

    def test_gitleaks_skips_severity_and_risk_type(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "gitleaks"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == []

    def test_nmap_no_fields_to_enrich(self, pipeline: EnrichmentPipeline) -> None:
        metadata = {"tool": "nmap"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == []

    def test_skips_field_if_already_has_value(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "nmap", "risk_type": "exposed_service"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "risk_type" not in fields

    def test_invalid_severity_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"severity": "CRITICAL", "risk_type": "xss"}
        result = pipeline._validate_response(raw, ["severity", "risk_type"])
        assert "severity" not in result
        assert result.get("risk_type") == "xss"

    def test_non_snake_case_risk_type_omitted(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        raw = {"risk_type": "Cross Site Scripting"}
        result = pipeline._validate_response(raw, ["risk_type"])
        assert "risk_type" not in result

    def test_unexpected_fields_ignored(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"risk_type": "xss", "evil_field": "x"}
        result = pipeline._validate_response(raw, ["risk_type"])
        assert "evil_field" not in result
        assert result.get("risk_type") == "xss"

    def test_empty_string_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"risk_type": ""}
        result = pipeline._validate_response(raw, ["risk_type"])
        assert "risk_type" not in result

    def test_valid_response_passes_through(self, pipeline: EnrichmentPipeline) -> None:
        raw = {
            "risk_type": "exposed_service",
            "remediation": "Block the port via firewall.",
            "severity": "medium",
            "confidence": "probable",
            "description": "Port 22 is open and accessible.",
        }
        fields = list(raw.keys())
        result = pipeline._validate_response(raw, fields)
        assert result == raw

    def test_invalid_confidence_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"confidence": "high"}
        result = pipeline._validate_response(raw, ["confidence"])
        assert "confidence" not in result

    def test_valid_confidence_passes_through(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        raw = {"confidence": "confirmed"}
        result = pipeline._validate_response(raw, ["confidence"])
        assert result.get("confidence") == "confirmed"

    def test_gitleaks_skips_confidence(self, pipeline: EnrichmentPipeline) -> None:
        metadata = {"tool": "gitleaks"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "confidence" not in fields

    def test_semgrep_confidence_requested_from_llm(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "semgrep"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "confidence" in fields
