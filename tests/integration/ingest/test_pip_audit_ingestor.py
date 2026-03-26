"""Integration tests for the pip-audit → ChromaDB ingestion pipeline."""

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
from infrastructure.tools.parsers.pip_audit_parser import (  # noqa: E402
    parse_pip_audit_json,
)

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


def _parse_fixture(filename: str) -> dict:
    return parse_pip_audit_json(_FIXTURES / filename)


def _make_pip_audit_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="pip-audit",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
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


@pytest.fixture()
def vulns_parsed_data() -> dict:
    return _parse_fixture("pip_audit_vulns.json")


@pytest.fixture()
def no_vulns_parsed_data() -> dict:
    return _parse_fixture("pip_audit_no_vulns.json")


class TestPipAuditIngestor:
    def test_count_matches_vulnerabilities(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """2 vulnerabilities in fixture → 2 documents ingested."""
        n_vulns = len(vulns_parsed_data["vulnerabilities"])
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert len(ingested) == n_vulns
        assert engine.count_documents() == n_vulns

    def test_zero_vulns_ingests_nothing(
        self, project_env: dict, no_vulns_parsed_data: dict
    ) -> None:
        """0 vulnerabilities → 0 documents, no error."""
        result = _make_pip_audit_result(no_vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert ingested == []
        assert engine.count_documents() == 0

    def test_metadata_fields_always_present(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """All required metadata fields are present on every document."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        required = {
            "tool",
            "profile",
            "finding_type",
            "severity",
            "package_name",
            "package_version",
            "vulnerability_id",
            "ecosystem",
            "timestamp",
            "source_file",
        }
        for meta in all_docs["metadatas"]:
            missing = required - meta.keys()
            assert not missing, f"Missing metadata fields: {missing}"

    def test_metadata_field_values(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Metadata field values match the parsed fixture data."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        fixture_vulns = {
            v["vulnerability_id"]: v for v in vulns_parsed_data["vulnerabilities"]
        }
        for meta in all_docs["metadatas"]:
            assert meta["tool"] == "pip-audit"
            assert meta["profile"] == "test-repo"
            assert meta["finding_type"] == '["dependency"]'
            vuln_id = meta["vulnerability_id"]
            assert vuln_id in fixture_vulns, f"Unknown vuln_id in metadata: {vuln_id}"
            expected = fixture_vulns[vuln_id]
            assert meta["package_name"] == expected["package_name"]
            assert meta["package_version"] == expected["package_version"]
            assert meta["severity"] == expected["severity"]
            assert meta["ecosystem"] == expected["affected_ecosystem"]

    def test_fixed_version_in_metadata_when_present(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """fixed_version key is present when the parser produces one."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        requests_metas = [
            m for m in all_docs["metadatas"] if m["vulnerability_id"] == "PYSEC-2023-74"
        ]
        assert len(requests_metas) == 1
        assert "fixed_version" in requests_metas[0], (
            "fixed_version must be present when parser produces a non-None value"
        )
        assert requests_metas[0]["fixed_version"] == "2.31.0"

    def test_fixed_version_absent_from_metadata_when_none(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """fixed_version key is absent when fix_versions list is empty."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        pillow_metas = [
            m
            for m in all_docs["metadatas"]
            if m["vulnerability_id"] == "PYSEC-2023-175"
        ]
        assert len(pillow_metas) == 1
        assert "fixed_version" not in pillow_metas[0], (
            "fixed_version must be absent when fixed_version is None"
        )

    def test_lockfile_never_in_pip_audit_metadata(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """'lockfile' key is never added to pip-audit metadata."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert "lockfile" not in meta, (
                f"'lockfile' key must never appear in pip-audit metadata: {meta}"
            )

    def test_text_template_with_fixed_version(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Document text contains package name and vulnerability id."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        requests_docs = [
            d
            for d, m in zip(all_docs["documents"], all_docs["metadatas"])
            if m["vulnerability_id"] == "PYSEC-2023-74"
        ]
        assert len(requests_docs) == 1
        assert "requests" in requests_docs[0]
        assert "PYSEC-2023-74" in requests_docs[0]

    def test_text_template_without_fixed_version(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Document text contains package name and vulnerability id."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        pillow_docs = [
            d
            for d, m in zip(all_docs["documents"], all_docs["metadatas"])
            if m["vulnerability_id"] == "PYSEC-2023-175"
        ]
        assert len(pillow_docs) == 1
        assert "pillow" in pillow_docs[0]
        assert "PYSEC-2023-175" in pillow_docs[0]

    def test_tool_name_in_text_and_metadata(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Document text starts with '[pip-audit]' and metadata tool is 'pip-audit'."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for text, meta in zip(all_docs["documents"], all_docs["metadatas"]):
            assert text.startswith("[pip-audit]"), (
                f"Document text must start with '[pip-audit]', got: {text[:40]!r}"
            )
            assert meta["tool"] == "pip-audit"

    def test_no_duplicates(self, project_env: dict, vulns_parsed_data: dict) -> None:
        """Ingesting the same data twice does not double the document count."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])
        ingestor.ingest_tool_output(result, profile="test-repo")
        count_after_first = engine.count_documents()
        ingestor.ingest_tool_output(result, profile="test-repo")
        assert engine.count_documents() == count_after_first

    def test_two_profiles_independent(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Two profiles coexist; re-ingesting one does not affect the other."""
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])

        result_a = _make_pip_audit_result(vulns_parsed_data)
        ingestor.ingest_tool_output(result_a, profile="profile-a")
        count_a = engine.count_documents()

        result_b = _make_pip_audit_result(vulns_parsed_data)
        ingestor.ingest_tool_output(result_b, profile="profile-b")
        total = engine.count_documents()
        assert total == count_a * 2

        ingestor.ingest_tool_output(result_a, profile="profile-a")
        assert engine.count_documents() == total

    def test_shared_metadata_fields(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """pip-audit chunks have correct domain/enriched/type_* fields."""
        result = _make_pip_audit_result(vulns_parsed_data)
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
            assert meta["type_secret"] is False
            assert meta["type_weakness"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_exposure"] is False
