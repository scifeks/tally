"""Integration tests: gitleaks bypasses LLM for risk_type entirely."""

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

        assert not captured_fields, "LLM must not be called for gitleaks"

    def test_semgrep_still_receives_risk_type_from_llm(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["SQL injection in login.py line 42"],
            metadatas=[
                {
                    "tool": "semgrep",
                    "enriched": False,
                    "severity": "confirmed",
                }
            ],
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
