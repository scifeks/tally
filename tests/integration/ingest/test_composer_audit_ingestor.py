"""Integration tests for the composer-audit → ChromaDB ingestion pipeline."""

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
from application.rag import FindingIngestor, RAGEngine  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


def _make_sca_result(tool_name: str, parsed_data: dict) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files={},
        timestamp=RAGEngine.now_iso(),
        duration_seconds=0.1,
    )


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
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/gitleaks",
                },
                "nmap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/nmap",
                },
                "pip-audit": {
                    "type": "repo",
                    "location": "local",
                    "path": "/home/justin/.local/bin/pip-audit",
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


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


class TestComposerAuditIngestor:
    @pytest.fixture()
    def composer_parsed_data(self) -> dict:
        raw = json.loads((_FIXTURES / "composer_audit_vulns.json").read_text())
        vulns = []
        for v in raw["vulnerabilities"]:
            entry: dict = {
                "package_name": v["package_name"],
                "package_version": v["package_version"],
                "vulnerability_id": v["vulnerability_id"],
                "severity": v["severity"],
                "summary": v["summary"],
                "affected_ecosystem": v["affected_ecosystem"],
                "fixed_version": v.get("fixed_version"),
                "cvss_score": v.get("cvss_score"),
                "source_file": v.get("source_file") or "",
            }
            vulns.append(entry)
        return {"vulnerabilities": vulns, "summary": raw["summary"]}

    def test_shared_metadata(
        self, project_env: dict, composer_parsed_data: dict
    ) -> None:
        result = _make_sca_result("composer-audit", composer_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert meta["domain"] == "code"
            assert meta["enriched"] is False
            assert meta["type_dependency"] is True
            assert meta["type_vulnerability"] is True

    def test_fixed_version_absent(
        self, project_env: dict, composer_parsed_data: dict
    ) -> None:
        result = _make_sca_result("composer-audit", composer_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        meta = all_docs["metadatas"][0]
        assert "fixed_version" not in meta

    def test_return_type_is_list(
        self, project_env: dict, composer_parsed_data: dict
    ) -> None:
        result = _make_sca_result("composer-audit", composer_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == len(composer_parsed_data["vulnerabilities"])
        assert all(isinstance(i, str) for i in doc_ids)
