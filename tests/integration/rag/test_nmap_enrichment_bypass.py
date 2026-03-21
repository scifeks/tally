"""Integration tests: nmap bypasses LLM enrichment entirely."""

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


class TestNmapEnrichmentBypass:
    def test_nmap_zero_llm_calls(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env)
        engine.add_documents(
            texts=["[nmap] Port 22/tcp on 10.0.0.1: ssh"],
            metadatas=[
                {
                    "tool": "nmap",
                    "enriched": False,
                    "severity": "informational",
                }
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
                {
                    "tool": "nmap",
                    "enriched": False,
                    "severity": "informational",
                }
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
            metadatas=[
                {
                    "tool": "semgrep",
                    "enriched": False,
                    "severity": "confirmed",
                }
            ],
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
