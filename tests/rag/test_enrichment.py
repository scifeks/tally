"""Tests for EnrichmentPipeline."""

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
from core.rag import EnrichmentPipeline, RAGEngine  # noqa: E402
from core.tools.constants import ENRICHMENT_FIELDS  # noqa: E402

_OLLAMA_URL = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_global_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama_base_url": _OLLAMA_URL,
                "default_llm": "qwen3:14b",
                "default_embedding": "nomic-embed-text:latest",
            }
        )
    )


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
    """Return a valid LLM response dict for the given fields."""
    values = {
        "risk_type": "exposed_service",
        "remediation": "Restrict access to this port via firewall rules.",
        "severity": "potential",
        "description": "An open port was found exposing a potentially exploitable service.",  # noqa: E501
    }
    return {f: values[f] for f in fields if f in values}


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
def seeded_engine(project_env: dict) -> RAGEngine:
    engine = _make_rag_engine(project_env)
    # doc 1: gitleaks — enriched=False, severity already set (tool-provided), needs rest
    engine.add_documents(
        texts=["Leaked AWS access key found in config.py"],
        metadatas=[{"tool": "gitleaks", "enriched": False, "severity": "confirmed"}],
        ids=["gl-001"],
    )
    # doc 2: zap — enriched=False, sev/rem/desc already in meta, only risk_type needed
    engine.add_documents(
        texts=["Reflected XSS found in search parameter"],
        metadatas=[
            {
                "tool": "zap",
                "enriched": False,
                "severity": "confirmed",
                "remediation": "Encode output.",
                "description": "XSS via search param.",
            }
        ],
        ids=["zap-001"],
    )
    # doc 3: nmap — enriched=True (already done, should be skipped)
    engine.add_documents(
        texts=["Port 22 SSH open on 10.0.0.1"],
        metadatas={"tool": "nmap", "enriched": True, "risk_type": "exposed_service"},  # type: ignore[arg-type]
        ids=["nm-001"],
    )
    return engine


@pytest.fixture()
def pipeline(seeded_engine: RAGEngine) -> EnrichmentPipeline:
    return EnrichmentPipeline(seeded_engine, console=None)


# ---------------------------------------------------------------------------
# TestEnrichmentPipeline — pipeline-level
# ---------------------------------------------------------------------------


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
        # zap with all 4 enrichment fields already present
        engine.add_documents(
            texts=["SQL injection in login form"],
            metadatas=[
                {
                    "tool": "zap",
                    "enriched": False,
                    "risk_type": "sql_injection",
                    "severity": "confirmed",
                    "remediation": "Use parameterized queries.",
                    "description": "SQL injection found in login form.",
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
            return_value=_make_llm_response(
                ["risk_type", "remediation", "description"]
            ),
        ) as mock_llm:
            pipeline.enrich(["gl-001"])
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
        fields = ["risk_type", "remediation", "description"]
        llm_response = _make_llm_response(fields)
        with patch.object(pipeline, "_call_llm", return_value=llm_response):
            pipeline.enrich(["gl-001"])
        doc = seeded_engine.get_document_by_id("gl-001")
        assert doc is not None
        for field in fields:
            assert field in doc["metadata"]
            assert doc["metadata"][field] == llm_response[field]

    def test_invalid_json_leaves_enriched_false(
        self, pipeline: EnrichmentPipeline, seeded_engine: RAGEngine
    ) -> None:
        with patch.object(
            pipeline, "_call_llm", side_effect=json.JSONDecodeError("err", "", 0)
        ):
            pipeline.enrich(["gl-001"])
        doc = seeded_engine.get_document_by_id("gl-001")
        assert doc is not None
        assert not doc["metadata"].get("enriched")

    def test_pipeline_continues_after_one_failure(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["Finding A"],
            metadatas=[{"tool": "nmap", "enriched": False}],
            ids=["cont-001"],
        )
        engine.add_documents(
            texts=["Finding B"],
            metadatas=[{"tool": "nmap", "enriched": False}],
            ids=["cont-002"],
        )
        p = EnrichmentPipeline(engine, console=None)
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise json.JSONDecodeError("bad", "", 0)
            return _make_llm_response(list(ENRICHMENT_FIELDS))

        with patch.object(p, "_call_llm", side_effect=side_effect):
            p.enrich(["cont-001", "cont-002"])

        doc2 = engine.get_document_by_id("cont-002")
        assert doc2 is not None
        assert doc2["metadata"].get("enriched") is True

    def test_idempotent_second_run_skips(self, pipeline: EnrichmentPipeline) -> None:
        fields = ["risk_type", "remediation", "description"]
        with patch.object(
            pipeline, "_call_llm", return_value=_make_llm_response(fields)
        ) as mock_llm:
            pipeline.enrich(["gl-001"])
            pipeline.enrich(["gl-001"])
            assert mock_llm.call_count == 1

    # -------------------------------------------------------------------
    # Field skip logic (_get_fields_to_enrich)
    # -------------------------------------------------------------------

    def test_zap_skips_remediation_severity_description(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "zap"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == ["risk_type"]

    def test_gitleaks_skips_severity(self, pipeline: EnrichmentPipeline) -> None:
        metadata = {"tool": "gitleaks"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "severity" not in fields
        assert "risk_type" in fields
        assert "remediation" in fields

    def test_nmap_enriches_all_fields(self, pipeline: EnrichmentPipeline) -> None:
        metadata = {"tool": "nmap"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert set(fields) == set(ENRICHMENT_FIELDS)

    def test_skips_field_if_already_has_value(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "nmap", "risk_type": "exposed_service"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "risk_type" not in fields

    # -------------------------------------------------------------------
    # Response validation (_validate_response)
    # -------------------------------------------------------------------

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
            "severity": "potential",
            "description": "Port 22 is open and accessible.",
        }
        fields = list(raw.keys())
        result = pipeline._validate_response(raw, fields)
        assert result == raw
