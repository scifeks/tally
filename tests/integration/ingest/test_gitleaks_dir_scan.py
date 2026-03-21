"""Integration tests for gitleaks dir-scan → ChromaDB ingestion."""

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
from infrastructure.tools.parsers.gitleaks_parser import (  # noqa: E402
    parse_gitleaks_json,
)

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


def _parse_fixture(filename: str) -> dict:
    return parse_gitleaks_json(_FIXTURES / filename)


def _make_gitleaks_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="gitleaks",
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
def dir_parsed_data() -> dict:
    return _parse_fixture("gitleaks_dir.json")


class TestGitleaksDirScan:
    def test_count(self, project_env: dict, dir_parsed_data: dict) -> None:
        """Ingested document count matches number of secrets in fixture."""
        n_secrets = len(dir_parsed_data["secrets"])
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert len(ingested) == n_secrets
        assert engine.count_documents() == n_secrets

    def test_identity(self, project_env: dict, dir_parsed_data: dict) -> None:
        """Every ingested document ID is retrievable from ChromaDB."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        stored_ids = set(all_docs["ids"])
        assert engine._collection is not None
        for doc_id in stored_ids:
            fetched = engine._collection.get(ids=[doc_id])
            assert fetched["ids"] == [doc_id], f"Document {doc_id!r} not retrievable"

    def test_metadata_fidelity(self, project_env: dict, dir_parsed_data: dict) -> None:
        """Every metadata field matches the expected value from the fixture."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        metadatas = all_docs["metadatas"]
        assert len(metadatas) == len(dir_parsed_data["secrets"])

        for i, (meta, secret) in enumerate(zip(metadatas, dir_parsed_data["secrets"])):
            tags_str = ", ".join(secret.get("tags") or [])
            expected = {
                "tool": "gitleaks",
                "profile": "test-repo",
                "finding_type": '["secret"]',
                "severity": "high",
                "confidence": "confirmed",
                "rule_id": secret["rule_id"],
                "file_path": secret["file_path"],
                "line_number": secret["line_number"],
                "tags": tags_str,
                "source_file": "",
            }
            for field, expected_val in expected.items():
                assert meta.get(field) == expected_val, (
                    f"Secret #{i}: metadata field {field!r} mismatch. "
                    f"Expected {expected_val!r}, got {meta.get(field)!r}"
                )
            assert "timestamp" in meta, (
                f"Secret #{i}: 'timestamp' key absent from metadata"
            )

    def test_content_accuracy(self, project_env: dict, dir_parsed_data: dict) -> None:
        """Document text matches the exact expected template."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        stored_texts = all_docs["documents"]
        stored_metas = all_docs["metadatas"]

        for text, meta in zip(stored_texts, stored_metas):
            rule_id = meta["rule_id"]
            file_path = meta["file_path"]
            line_number = meta["line_number"]
            assert (
                f"[gitleaks] Secret detected: {rule_id} in {file_path}:{line_number}"
            ) in text
            assert "Note: Secret value redacted" in text

    def test_no_commit_in_dir_scan(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Dir-scan documents must NOT have a 'commit' key in metadata."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert "commit" not in meta, (
                f"'commit' key must be absent from dir-scan metadata, got: {meta}"
            )

    def test_no_duplicates(self, project_env: dict, dir_parsed_data: dict) -> None:
        """Ingesting the same data twice does not double the document count."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])
        ingestor.ingest_tool_output(result, profile="test-repo")
        count_after_first = engine.count_documents()
        ingestor.ingest_tool_output(result, profile="test-repo")
        count_after_second = engine.count_documents()
        assert count_after_second == count_after_first, (
            f"Duplicate ingest inflated count: {count_after_first}"
            f" → {count_after_second}"
        )

    def test_empty_findings(self, project_env: dict) -> None:
        """Ingesting an empty secrets list adds 0 documents and raises no error."""
        empty_data = {
            "secrets": [],
            "summary": {
                "total_secrets": 0,
                "by_rule": {},
                "files_with_secrets": 0,
            },
        }
        result = _make_gitleaks_result(empty_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert ingested == []
        assert engine.count_documents() == 0

    def test_ingest_replaces_stale(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Ingesting under a different profile creates independent sets."""
        result_a = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])
        ingestor.ingest_tool_output(result_a, profile="profile-a")
        count_a = engine.count_documents()

        result_b = _make_gitleaks_result(dir_parsed_data)
        ingestor.ingest_tool_output(result_b, profile="profile-b")
        total = engine.count_documents()

        assert total == count_a * 2, (
            f"Expected {count_a * 2} docs after two profiles, got {total}"
        )

        ingestor.ingest_tool_output(result_a, profile="profile-a")
        assert engine.count_documents() == total, (
            "Re-ingest of profile-a changed total — "
            "profile-b contaminated or profile-a not replaced"
        )

    def test_shared_metadata_fields(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Gitleaks chunks have correct domain/enriched/type_* fields."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert meta["domain"] == "code"
            assert meta["enriched"] is False
            assert meta["type_secret"] is True
            assert meta["type_vulnerability"] is False
            assert meta["type_weakness"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_exposure"] is False
            assert meta["type_dependency"] is False

    def test_text_no_match_value(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Document text must not have 'Pattern matched'; must have redaction."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for text in all_docs["documents"]:
            assert "Pattern matched" not in text
            assert "Note: Secret value redacted" in text
