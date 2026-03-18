"""Tests for EnrichmentPipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.project import ProjectManager  # noqa: E402
from core.rag import EnrichmentPipeline, RAGEngine  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402

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
    # doc 2: zap — enriched=False, sev/rem/desc already in meta, only risk_type needed
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
        # zap with all enrichment fields already present
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
                }
            ],
            ids=["zap-full-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich(["zap-full-001"])
            mock_llm.assert_not_called()

    def test_missing_fields_calls_llm_once(self, pipeline: EnrichmentPipeline) -> None:
        # zap-001 is missing risk_type → exactly one LLM call expected
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
        # zap-001: severity/remediation/description tool-provided; LLM fills risk_type
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
        # zap-001 needs risk_type from LLM; simulate a bad JSON response
        with patch.object(
            pipeline, "_call_llm", side_effect=json.JSONDecodeError("err", "", 0)
        ):
            pipeline.enrich(["zap-001"])
        doc = seeded_engine.get_document_by_id("zap-001")
        assert doc is not None
        assert not doc["metadata"].get("enriched")

    def test_pipeline_continues_after_one_failure(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        # Use semgrep (calls LLM) to verify the pipeline continues past one failure
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
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise json.JSONDecodeError("bad", "", 0)
            return _make_llm_response(["risk_type", "remediation", "description"])

        with patch.object(p, "_call_llm", side_effect=side_effect):
            p.enrich(["cont-001", "cont-002"])

        doc2 = engine.get_document_by_id("cont-002")
        assert doc2 is not None
        assert doc2["metadata"].get("enriched") is True

    def test_idempotent_second_run_skips(self, pipeline: EnrichmentPipeline) -> None:
        # zap-001 needs risk_type; second call should skip (already enriched=True)
        fields = ["risk_type"]
        with patch.object(
            pipeline, "_call_llm", return_value=_make_llm_response(fields)
        ) as mock_llm:
            pipeline.enrich(["zap-001"])
            pipeline.enrich(["zap-001"])
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

    def test_gitleaks_skips_severity_and_risk_type(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        # gitleaks has should_enrich=False — no fields requested from LLM
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
            "severity": "medium",
            "confidence": "probable",
            "description": "Port 22 is open and accessible.",
        }
        fields = list(raw.keys())
        result = pipeline._validate_response(raw, fields)
        assert result == raw

    def test_invalid_confidence_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"confidence": "high"}  # "high" is a severity value, not a confidence
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


# ---------------------------------------------------------------------------
# TestNmapEnrichmentBypass — nmap bypasses LLM entirely
# ---------------------------------------------------------------------------


class TestNmapEnrichmentBypass:
    def test_nmap_zero_llm_calls(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["[nmap] Port 22/tcp on 10.0.0.1: ssh"],
            metadatas=[
                {"tool": "nmap", "enriched": False, "severity": "informational"}
            ],
            ids=["nmap-bypass-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich(["nmap-bypass-001"])
            mock_llm.assert_not_called()

    def test_nmap_enriched_true_after_pipeline(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["[nmap] Host: 10.0.0.1\nStatus: up"],
            metadatas=[
                {"tool": "nmap", "enriched": False, "severity": "informational"}
            ],
            ids=["nmap-bypass-002"],
        )
        p = EnrichmentPipeline(engine, console=None)
        with patch.object(p, "_call_llm"):
            p.enrich(["nmap-bypass-002"])
        doc = engine.get_document_by_id("nmap-bypass-002")
        assert doc is not None
        assert doc["metadata"].get("enriched") is True

    def test_semgrep_still_calls_llm(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["SQL injection in login.py line 42"],
            metadatas=[{"tool": "semgrep", "enriched": False, "severity": "confirmed"}],
            ids=["semgrep-regression-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        fields = ["risk_type", "remediation", "description"]
        with patch.object(
            p, "_call_llm", return_value=_make_llm_response(fields)
        ) as mock_llm:
            p.enrich(["semgrep-regression-001"])
            mock_llm.assert_called_once()

    def test_zap_still_calls_llm(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["Reflected XSS in search param"],
            metadatas=[
                {
                    "tool": "zap",
                    "enriched": False,
                    "severity": "high",
                    "remediation": "Encode output.",
                    "description": "XSS via search param.",
                }
            ],
            ids=["zap-regression-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        with patch.object(
            p, "_call_llm", return_value=_make_llm_response(["risk_type"])
        ) as mock_llm:
            p.enrich(["zap-regression-001"])
            mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# TestNmapIngestorMetadata — chunk builders produce correct metadata
# ---------------------------------------------------------------------------


class TestNmapIngestorMetadata:
    def _make_nmap_result(self) -> ToolResult:
        return ToolResult(
            tool_name="nmap",
            success=True,
            output="",
            parsed_data={
                "hosts": [
                    {
                        "ip_address": "10.0.0.1",
                        "hostname": "target.local",
                        "state": "up",
                        "ports": [
                            {
                                "port": 22,
                                "transport": "tcp",
                                "state": "open",
                                "service": "ssh",
                                "service_version": "",
                            }
                        ],
                    }
                ]
            },
            output_files={},
            timestamp="2024-01-01T00:00:00",
            duration_seconds=0.1,
        )

    def _get_chunks(self):
        from core.rag.ingestor import FindingIngestor

        ingestor = FindingIngestor(MagicMock(), "test-proj")
        return ingestor._build_chunks(self._make_nmap_result(), "default")

    def test_host_chunk_severity_informational(self) -> None:
        chunks = self._get_chunks()
        host_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" not in c[1]
        ]
        assert host_chunks, "Expected at least one host chunk"
        assert host_chunks[0][1]["severity"] == "informational"

    def test_open_port_chunk_severity_informational(self) -> None:
        chunks = self._get_chunks()
        port_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" in c[1]
        ]
        assert port_chunks, "Expected at least one open_port chunk"
        assert port_chunks[0][1]["severity"] == "informational"

    def test_host_chunk_no_risk_type(self) -> None:
        chunks = self._get_chunks()
        host_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" not in c[1]
        ]
        assert "risk_type" not in host_chunks[0][1]

    def test_open_port_chunk_no_risk_type(self) -> None:
        chunks = self._get_chunks()
        port_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" in c[1]
        ]
        assert "risk_type" not in port_chunks[0][1]

    def test_no_type_boolean_true(self) -> None:
        chunks = self._get_chunks()
        for _text, meta, _id in chunks:
            for key, val in meta.items():
                if key.startswith("type_"):
                    assert val is not True, f"{key} should not be True for nmap chunks"


# ---------------------------------------------------------------------------
# TestGitleaksIngestorMetadata — gitleaks chunk builder produces correct metadata
# ---------------------------------------------------------------------------


class TestGitleaksIngestorMetadata:
    def _make_gitleaks_result(self, rule_id: str) -> ToolResult:
        return ToolResult(
            tool_name="gitleaks",
            success=True,
            output="",
            parsed_data={
                "secrets": [
                    {
                        "rule_id": rule_id,
                        "description": "AWS Access Token",
                        "file_path": "config.py",
                        "line_number": 42,
                        "tags": ["aws"],
                        "commit": "abc123",
                        "fingerprint": "fp-001",
                    }
                ],
                "summary": {"total": 1},
            },
            output_files={},
            timestamp="2024-01-01T00:00:00",
            duration_seconds=0.1,
        )

    def _get_chunks(self, rule_id: str):
        from core.rag.ingestor import FindingIngestor

        ingestor = FindingIngestor(MagicMock(), "test-proj")
        return ingestor._build_chunks(self._make_gitleaks_result(rule_id), "default")

    def test_known_rule_id_sets_risk_type(self) -> None:
        chunks = self._get_chunks("aws-access-token")
        assert len(chunks) == 1
        assert chunks[0][1]["risk_type"] == "aws-access-token"

    def test_empty_rule_id_omits_risk_type(self) -> None:
        chunks = self._get_chunks("")
        assert len(chunks) == 1
        assert "risk_type" not in chunks[0][1]

    def test_generic_api_key_rule_id_sets_risk_type(self) -> None:
        chunks = self._get_chunks("generic-api-key")
        assert chunks[0][1]["risk_type"] == "generic-api-key"

    def test_jwt_rule_id_sets_risk_type(self) -> None:
        chunks = self._get_chunks("jwt")
        assert chunks[0][1]["risk_type"] == "jwt"


# ---------------------------------------------------------------------------
# TestGitleaksEnrichmentBypass — gitleaks bypasses LLM for risk_type entirely
# ---------------------------------------------------------------------------


class TestGitleaksEnrichmentBypass:
    def test_gitleaks_with_rule_id_zero_llm_calls(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["[gitleaks] Secret detected: aws-access-token in config.py:42"],
            metadatas=[
                {
                    "tool": "gitleaks",
                    "enriched": False,
                    "severity": "high",
                    "risk_type": "aws-access-token",
                    "remediation": "Rotate the key and remove from repository.",
                    "description": "AWS access token found in source file.",
                }
            ],
            ids=["gl-bypass-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich(["gl-bypass-001"])
            mock_llm.assert_not_called()

    def test_gitleaks_risk_type_not_requested_from_llm(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        # No risk_type in metadata — but it's tool-provided so LLM must not be asked
        engine.add_documents(
            texts=["[gitleaks] Secret detected: generic-api-key in .env:5"],
            metadatas=[{"tool": "gitleaks", "enriched": False, "severity": "high"}],
            ids=["gl-bypass-002"],
        )
        p = EnrichmentPipeline(engine, console=None)
        captured_fields: list[list[str]] = []

        def capture_call(doc_text, metadata, fields):
            captured_fields.append(list(fields))
            return _make_llm_response(fields)

        with patch.object(p, "_call_llm", side_effect=capture_call):
            p.enrich(["gl-bypass-002"])

        # gitleaks has should_enrich=False — LLM must not be called at all
        assert not captured_fields, "LLM must not be called for gitleaks"

    def test_semgrep_still_receives_risk_type_from_llm(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["SQL injection in login.py line 42"],
            metadatas=[{"tool": "semgrep", "enriched": False, "severity": "confirmed"}],
            ids=["semgrep-bypass-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        captured_fields: list[list[str]] = []

        def capture_call(doc_text, metadata, fields):
            captured_fields.append(list(fields))
            return _make_llm_response(fields)

        with patch.object(p, "_call_llm", side_effect=capture_call):
            p.enrich(["semgrep-bypass-001"])

        assert captured_fields, "LLM should be called for semgrep"
        assert "risk_type" in captured_fields[0]

    def test_zap_still_receives_risk_type_from_llm(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["Reflected XSS in search param"],
            metadatas=[
                {
                    "tool": "zap",
                    "enriched": False,
                    "severity": "high",
                    "remediation": "Encode output.",
                    "description": "XSS via search param.",
                }
            ],
            ids=["zap-bypass-001"],
        )
        p = EnrichmentPipeline(engine, console=None)
        captured_fields: list[list[str]] = []

        def capture_call(doc_text, metadata, fields):
            captured_fields.append(list(fields))
            return _make_llm_response(fields)

        with patch.object(p, "_call_llm", side_effect=capture_call):
            p.enrich(["zap-bypass-001"])

        assert captured_fields, "LLM should be called for zap"
        assert "risk_type" in captured_fields[0]
