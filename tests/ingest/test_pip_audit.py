"""Integration tests for the pip-audit → ChromaDB ingestion pipeline.

Run from the tally project root:
    pytest tests/ingest/test_pip_audit.py -v
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.project import ProjectManager  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.pip_audit_parser import (  # noqa: E402
    parse_pip_audit_json,
    parse_pip_audit_json_string,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Parser unit tests  (no binary, no Ollama, no ChromaDB)
# ---------------------------------------------------------------------------


class TestPipAuditParser:
    def test_parse_json_string_basic(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "django",
                        "version": "3.2.0",
                        "vulns": [
                            {
                                "id": "PYSEC-2024-1",
                                "description": "SQL injection in ORM",
                                "fix_versions": ["3.2.20"],
                                "severity": "CRITICAL",
                            }
                        ],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert "vulnerabilities" in parsed
        assert len(parsed["vulnerabilities"]) == 1
        vuln = parsed["vulnerabilities"][0]
        assert vuln["vulnerability_id"] == "PYSEC-2024-1"
        assert vuln["package_name"] == "django"
        assert vuln["package_version"] == "3.2.0"
        assert vuln["severity"] == "critical"
        assert vuln["fixed_version"] == "3.2.20"

    def test_parse_error_returns_error_key(self) -> None:
        result = parse_pip_audit_json_string("not json {{{{")
        assert "error" in result

    def test_severity_defaults_to_low(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [{"id": "X", "description": "", "fix_versions": []}],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["severity"] == "low"

    def test_severity_map_critical(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [
                            {
                                "id": "X",
                                "description": "",
                                "fix_versions": [],
                                "severity": "CRITICAL",
                            }
                        ],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["severity"] == "critical"

    def test_fixed_version_first_of_list(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [
                            {
                                "id": "X",
                                "description": "",
                                "fix_versions": ["1.1", "2.0"],
                            }
                        ],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["fixed_version"] == "1.1"

    def test_fixed_version_none_when_empty(self) -> None:
        raw = json.dumps(
            {
                "dependencies": [
                    {
                        "name": "pkg",
                        "version": "1.0",
                        "vulns": [{"id": "X", "description": "", "fix_versions": []}],
                    }
                ]
            }
        )
        parsed = parse_pip_audit_json_string(raw)
        assert parsed["vulnerabilities"][0]["fixed_version"] is None

    def test_cvss_score_always_none(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        for vuln in parsed["vulnerabilities"]:
            assert vuln["cvss_score"] is None, (
                f"cvss_score must always be None, got {vuln['cvss_score']!r}"
            )

    def test_source_file_always_empty_string(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        for vuln in parsed["vulnerabilities"]:
            assert vuln["source_file"] == "", (
                f"source_file must always be '', got {vuln['source_file']!r}"
            )

    def test_ecosystem_always_pypi(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        for vuln in parsed["vulnerabilities"]:
            assert vuln["affected_ecosystem"] == "PyPI"

    def test_summary_counts(self) -> None:
        parsed = _parse_fixture("pip_audit_vulns.json")
        summary = parsed["summary"]
        assert summary["total_vulnerabilities"] == 2
        assert summary["packages_scanned"] == 3
        assert summary["ecosystems"] == ["PyPI"]

    def test_no_vulns_produces_empty_list(self) -> None:
        parsed = _parse_fixture("pip_audit_no_vulns.json")
        assert parsed["vulnerabilities"] == []
        assert parsed["summary"]["total_vulnerabilities"] == 0


# ---------------------------------------------------------------------------
# Ingestor unit tests
# ---------------------------------------------------------------------------


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
        """fixed_version key is present in metadata when the parser produces one."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        # requests vuln (PYSEC-2023-74) has fix_versions=["2.31.0"]
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
        """fixed_version key is absent from metadata when fix_versions list is empty."""
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        # pillow vuln (PYSEC-2023-175) has fix_versions=[]
        pillow_metas = [
            m
            for m in all_docs["metadatas"]
            if m["vulnerability_id"] == "PYSEC-2023-175"
        ]
        assert len(pillow_metas) == 1
        assert "fixed_version" not in pillow_metas[0], (
            "fixed_version must be absent from metadata when fixed_version is None"
        )

    def test_lockfile_never_in_pip_audit_metadata(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """'lockfile' key is never added to pip-audit metadata.

        The pip-audit parser hardcodes source_file="" on every vuln, so the
        ingestor's conditional `if lockfile:` block is never entered.
        """
        result = _make_pip_audit_result(vulns_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert "lockfile" not in meta, (
                f"'lockfile' key must never appear in pip-audit metadata, got: {meta}"
            )

    def test_text_template_with_fixed_version(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Document text contains 'Fixed in: <version>' when fix is available."""
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
        assert "Fixed in: 2.31.0" in requests_docs[0]

    def test_text_template_without_fixed_version(
        self, project_env: dict, vulns_parsed_data: dict
    ) -> None:
        """Document text contains 'Fixed in: unknown' when no fix is available."""
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
        assert "Fixed in: unknown" in pillow_docs[0]

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


# ---------------------------------------------------------------------------
# SCA tool helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# npm-audit ingestor tests
# ---------------------------------------------------------------------------


class TestNpmAuditIngestor:
    @pytest.fixture()
    def npm_parsed_data(self) -> dict:
        raw = json.loads((_FIXTURES / "npm_audit_vulns.json").read_text())
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

    def test_tool_name_in_metadata(
        self, project_env: dict, npm_parsed_data: dict
    ) -> None:
        result = _make_sca_result("npm-audit", npm_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert meta["tool"] == "npm-audit"

    def test_shared_metadata(self, project_env: dict, npm_parsed_data: dict) -> None:
        result = _make_sca_result("npm-audit", npm_parsed_data)
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

    def test_metadata_fidelity(self, project_env: dict, npm_parsed_data: dict) -> None:
        result = _make_sca_result("npm-audit", npm_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        assert len(all_docs["metadatas"]) == len(npm_parsed_data["vulnerabilities"])
        meta = all_docs["metadatas"][0]
        vuln = npm_parsed_data["vulnerabilities"][0]
        assert meta["package_name"] == vuln["package_name"]
        assert meta["vulnerability_id"] == vuln["vulnerability_id"]
        assert meta["severity"] == vuln["severity"]

    def test_return_type_is_list(
        self, project_env: dict, npm_parsed_data: dict
    ) -> None:
        result = _make_sca_result("npm-audit", npm_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == len(npm_parsed_data["vulnerabilities"])
        assert all(isinstance(i, str) for i in doc_ids)


# ---------------------------------------------------------------------------
# osv-scanner ingestor tests
# ---------------------------------------------------------------------------


class TestOsvScannerIngestor:
    @pytest.fixture()
    def osv_parsed_data(self) -> dict:
        raw = json.loads((_FIXTURES / "osv_scanner_vulns.json").read_text())
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

    def test_shared_metadata(self, project_env: dict, osv_parsed_data: dict) -> None:
        result = _make_sca_result("osv-scanner", osv_parsed_data)
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

    def test_cvss_score_present(self, project_env: dict, osv_parsed_data: dict) -> None:
        result = _make_sca_result("osv-scanner", osv_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        meta = all_docs["metadatas"][0]
        assert "cvss_score" in meta
        assert isinstance(meta["cvss_score"], float)

    def test_lockfile_present(self, project_env: dict, osv_parsed_data: dict) -> None:
        result = _make_sca_result("osv-scanner", osv_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        meta = all_docs["metadatas"][0]
        assert "lockfile" in meta
        assert meta["lockfile"] == "requirements.txt"

    def test_return_type_is_list(
        self, project_env: dict, osv_parsed_data: dict
    ) -> None:
        result = _make_sca_result("osv-scanner", osv_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == len(osv_parsed_data["vulnerabilities"])
        assert all(isinstance(i, str) for i in doc_ids)


# ---------------------------------------------------------------------------
# composer-audit ingestor tests
# ---------------------------------------------------------------------------


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
