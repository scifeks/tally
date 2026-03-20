"""Integration tests for the gitleaks → ChromaDB ingestion pipeline.

Run from the tally project root:
    pytest tests/ingest/test_gitleaks.py -v -k "not Retrieval"

Skip markers:
    requires_ollama  — skipped when Ollama is not reachable
    requires_gitleaks — skipped when gitleaks binary is not installed
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]  # tests/ingest/ → tests/ → tally/
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config import ConfigManager  # noqa: E402
from core.project import ProjectManager  # noqa: E402
from core.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.rag.engine import verify_ollama_available  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402
from core.tools.parsers.gitleaks_parser import (  # noqa: E402
    _parse_secret,
    combine_gitleaks_results,
    parse_gitleaks_json,
)

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"


def _get_ollama_url() -> str | None:
    try:
        cfg = ConfigManager(base_path=str(_TALLY_ROOT))._load_global_config()
        return cfg.ollama.base_url if cfg.ollama else None
    except (FileNotFoundError, ValueError):
        return None


_OLLAMA_URL = _get_ollama_url()

requires_ollama = pytest.mark.skipif(
    _OLLAMA_URL is None or not verify_ollama_available(_OLLAMA_URL),
    reason="Ollama not configured or not running",
)
requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks binary not installed",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_fixture(filename: str) -> dict:
    """Parse a gitleaks fixture JSON file into structured data."""
    return parse_gitleaks_json(_FIXTURES / filename)


def _make_gitleaks_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    """Construct a synthetic ToolResult for gitleaks."""
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
    """Create a RAGEngine using chromadb's default embedding (no Ollama needed)."""
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        return RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )


def _get_all_docs(engine: RAGEngine) -> dict[str, list]:
    """Fetch all documents; normalises Optional fields to empty lists."""
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
    """Minimal project environment under tmp_path."""
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


@pytest.fixture()
def git_parsed_data() -> dict:
    return _parse_fixture("gitleaks_git.json")


@pytest.fixture()
def combined_parsed_data(dir_parsed_data: dict, git_parsed_data: dict) -> dict:
    return combine_gitleaks_results(dir_parsed_data, git_parsed_data)


# ---------------------------------------------------------------------------
# xfail tests: known bugs (written first, per constraints)
# ---------------------------------------------------------------------------


class TestKnownBugs:
    def test_combine_dedup_dir_git_shared_finding(
        self, dir_parsed_data: dict, git_parsed_data: dict
    ) -> None:
        """combine_gitleaks_results() deduplicates by (rule_id, file_path, line_number).
        The same secret from dir-scan and git-scan collapses to one entry."""
        combined = combine_gitleaks_results(dir_parsed_data, git_parsed_data)
        shared = [
            s
            for s in combined["secrets"]
            if s["rule_id"] == "aws-access-token"
            and s["file_path"] == "config/aws.js"
            and s["line_number"] == 10
        ]
        assert len(shared) == 1, (
            f"Expected 1 deduplicated entry for aws-access-token, got {len(shared)}."
        )

    def test_fingerprint_present_in_metadata(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """_chunks_from_gitleaks() stores the gitleaks Fingerprint field in metadata."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        metadatas = all_docs["metadatas"] or []
        assert metadatas, "No documents were ingested"
        for meta in metadatas:
            assert "fingerprint" in meta, (
                f"'fingerprint' key missing from metadata: {meta}"
            )
            assert meta["fingerprint"], "fingerprint value must not be empty"


# ---------------------------------------------------------------------------
# Dir-scan unit tests
# ---------------------------------------------------------------------------


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
                in text
            )
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
            "summary": {"total_secrets": 0, "by_rule": {}, "files_with_secrets": 0},
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
        """Ingesting under a different profile creates independent, isolated sets."""
        result_a = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])
        ingestor.ingest_tool_output(result_a, profile="profile-a")
        count_a = engine.count_documents()

        result_b = _make_gitleaks_result(dir_parsed_data)
        ingestor.ingest_tool_output(result_b, profile="profile-b")
        total = engine.count_documents()

        # Both profiles should coexist; total should be 2x single-profile count
        assert total == count_a * 2, (
            f"Expected {count_a * 2} docs after two profiles, got {total}"
        )

        # Re-ingesting profile-a should replace only its docs, not profile-b
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
        """Document text must not have 'Pattern matched'; must have redaction note."""
        result = _make_gitleaks_result(dir_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for text in all_docs["documents"]:
            assert "Pattern matched" not in text
            assert "Note: Secret value redacted" in text


# ---------------------------------------------------------------------------
# Git-scan unit tests
# ---------------------------------------------------------------------------


class TestGitleaksGitScan:
    def test_count(self, project_env: dict, git_parsed_data: dict) -> None:
        """Ingested count matches number of git-scan secrets."""
        n_secrets = len(git_parsed_data["secrets"])
        result = _make_gitleaks_result(git_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="git-repo")
        assert len(ingested) == n_secrets
        assert engine.count_documents() == n_secrets

    def test_commit_present_in_git_scan(
        self, project_env: dict, git_parsed_data: dict
    ) -> None:
        """Git-scan documents must have a non-empty 'commit' key in metadata."""
        result = _make_gitleaks_result(git_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="git-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert "commit" in meta, (
                f"'commit' key absent from git-scan metadata: {meta}"
            )
            assert meta["commit"], (
                f"'commit' value is empty in git-scan metadata: {meta}"
            )

    def test_content_accuracy_with_commit(
        self, project_env: dict, git_parsed_data: dict
    ) -> None:
        """Document text has correct content and commit is stored in metadata."""
        result = _make_gitleaks_result(git_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="git-repo"
        )
        all_docs = _get_all_docs(engine)
        for text, meta in zip(all_docs["documents"], all_docs["metadatas"]):
            rule_id = meta["rule_id"]
            file_path = meta["file_path"]
            line_number = meta["line_number"]
            assert (
                f"[gitleaks] Secret detected: {rule_id} in {file_path}:{line_number}"
                in text
            )

        # Verify commit values match fixture
        raw_fixture = json.load(open(_FIXTURES / "gitleaks_git.json"))
        commit_by_rule = {f["RuleID"]: f["Commit"] for f in raw_fixture}
        for meta in all_docs["metadatas"]:
            expected_commit = commit_by_rule.get(meta["rule_id"])
            assert meta.get("commit") == expected_commit, (
                f"Commit mismatch for rule {meta['rule_id']!r}: "
                f"expected {expected_commit!r}, got {meta.get('commit')!r}"
            )

    def test_metadata_fidelity(self, project_env: dict, git_parsed_data: dict) -> None:
        """Git-scan metadata fields are correct; severity is always 'high'."""
        result = _make_gitleaks_result(git_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="git-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert meta["tool"] == "gitleaks"
            assert meta["profile"] == "git-repo"
            assert meta["finding_type"] == '["secret"]'
            assert meta["severity"] == "high", (
                f"severity must always be 'high', got {meta['severity']!r}"
            )
            assert "commit" in meta

    def test_no_duplicates(self, project_env: dict, git_parsed_data: dict) -> None:
        """Ingesting the same git data twice does not double the document count."""
        result = _make_gitleaks_result(git_parsed_data)
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])
        ingestor.ingest_tool_output(result, profile="git-repo")
        count_after_first = engine.count_documents()
        ingestor.ingest_tool_output(result, profile="git-repo")
        assert engine.count_documents() == count_after_first


# ---------------------------------------------------------------------------
# Combined scan unit tests
# ---------------------------------------------------------------------------


class TestGitleaksCombinedScan:
    def test_combined_count(
        self, project_env: dict, combined_parsed_data: dict
    ) -> None:
        """Combined ingest count equals len(combined['secrets'])."""
        n = len(combined_parsed_data["secrets"])
        result = _make_gitleaks_result(combined_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="combined-repo")
        assert len(ingested) == n
        assert engine.count_documents() == n

    def test_combined_metadata_fidelity(
        self, project_env: dict, combined_parsed_data: dict
    ) -> None:
        """Every ingested doc matches a combined secret by rule+file+line."""
        result = _make_gitleaks_result(combined_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="combined-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            matching_secret = next(
                (
                    s
                    for s in combined_parsed_data["secrets"]
                    if s["rule_id"] == meta["rule_id"]
                    and s["file_path"] == meta["file_path"]
                    and s["line_number"] == meta["line_number"]
                ),
                None,
            )
            assert matching_secret is not None, (
                f"No matching secret found for metadata {meta}"
            )

    def test_deduplication_within_combined(
        self, project_env: dict, dir_parsed_data: dict, git_parsed_data: dict
    ) -> None:
        """The shared finding (same rule_id/file_path/line_number) appears exactly
        once after combine — dedup ignores commit so dir+git variants collapse."""
        combined = combine_gitleaks_results(dir_parsed_data, git_parsed_data)
        shared_entries = [
            s
            for s in combined["secrets"]
            if s["rule_id"] == "aws-access-token"
            and s["file_path"] == "config/aws.js"
            and s["line_number"] == 10
        ]
        assert len(shared_entries) == 1, (
            f"Expected 1 deduplicated entry, got {len(shared_entries)}"
        )
        result = _make_gitleaks_result(combined)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="combined-repo")
        assert len(ingested) == len(combined["secrets"]), (
            f"Ingested {len(ingested)} != combined count {len(combined['secrets'])}"
        )
        assert engine.count_documents() == len(combined["secrets"])


# ---------------------------------------------------------------------------
# Retrieval tests (requires Ollama)
# ---------------------------------------------------------------------------


class TestGitleaksRetrieval:
    @requires_ollama
    def test_semantic_search_by_rule_id(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Searching for a rule_id value returns the expected document in top-5."""
        from core.rag.query import QueryEngine

        result = _make_gitleaks_result(dir_parsed_data)
        engine = RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        try:
            FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
                result, profile="test-repo"
            )
            qe = QueryEngine(engine)
            results = qe.search("aws-access-token")
            assert results, "Expected at least one search result"
            found_tools = [r["metadata"]["tool"] for r in results]
            assert "gitleaks" in found_tools
        finally:
            engine.close()

    @requires_ollama
    def test_tool_filter_detection(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Querying 'what did gitleaks find?' applies tool filter in ChromaDB."""
        from core.rag.query import QueryEngine

        result = _make_gitleaks_result(dir_parsed_data)
        engine = RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        try:
            FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
                result, profile="test-repo"
            )
            qe = QueryEngine(engine)
            results = qe.search("what did gitleaks find?")
            assert results, "Expected results for tool-specific query"
            for r in results:
                assert r["metadata"]["tool"] == "gitleaks", (
                    f"Tool filter failed — got tool={r['metadata']['tool']!r}"
                )
        finally:
            engine.close()


# ---------------------------------------------------------------------------
# Parser unit tests  (no binary, no Ollama, no ChromaDB)
# ---------------------------------------------------------------------------


@pytest.fixture()
def raw_dir_findings() -> list:
    """Raw JSON array from gitleaks_dir.json — no parse_gitleaks_json() involved."""
    return json.loads((_FIXTURES / "gitleaks_dir.json").read_text())


@pytest.fixture()
def raw_git_findings() -> list:
    """Raw JSON array from gitleaks_git.json — no parse_gitleaks_json() involved."""
    return json.loads((_FIXTURES / "gitleaks_git.json").read_text())


class TestGitleaksParser:
    """Verify every field mapping in _parse_secret() against real fixture data."""

    def test_field_mapping_rule_id(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["rule_id"] == raw["RuleID"]

    def test_field_mapping_file_path(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["file_path"] == raw["File"]

    def test_field_mapping_line_number(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["line_number"] == raw["StartLine"]

    def test_field_mapping_description(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["description"] == raw["Description"]

    def test_field_mapping_tags_list_preserved(self, raw_dir_findings: list) -> None:
        raw = raw_dir_findings[0]
        parsed = _parse_secret(raw)
        assert parsed["tags"] == (raw["Tags"] or [])

    def test_field_mapping_commit_git_scan(self, raw_git_findings: list) -> None:
        """Non-empty Commit from git scan is preserved as-is."""
        raw = raw_git_findings[0]
        assert raw["Commit"], "git fixture must have a non-empty Commit"
        parsed = _parse_secret(raw)
        assert parsed["commit"] == raw["Commit"]

    def test_commit_empty_string_becomes_none(self) -> None:
        """Commit='' from a dir scan must be stored as None, not as empty string."""
        finding = {
            "RuleID": "aws-access-token",
            "File": "config/aws.js",
            "StartLine": 10,
            "Commit": "",
            "Secret": "AKIAZ3XYMWQ2LR7NVBPA",
            "Match": "AKIAZ3XYMWQ2LR7NVBPA",
            "Description": "test",
            "Tags": [],
        }
        parsed = _parse_secret(finding)
        assert parsed["commit"] is None, (
            f"Empty Commit string must map to None, got {parsed['commit']!r}"
        )

    def test_tags_none_becomes_empty_list(self) -> None:
        """Tags=null in raw JSON must become an empty list, not None."""
        finding = {
            "RuleID": "x",
            "File": "f.py",
            "StartLine": 1,
            "Commit": "",
            "Secret": "abc",
            "Match": "",
            "Description": "",
            "Tags": None,
        }
        parsed = _parse_secret(finding)
        assert parsed["tags"] == [], f"Tags=null must map to [], got {parsed['tags']!r}"

    def test_summary_counts(self) -> None:
        """parse_gitleaks_json summary.total_secrets matches len of raw array."""
        raw = json.loads((_FIXTURES / "gitleaks_dir.json").read_text())
        parsed = parse_gitleaks_json(_FIXTURES / "gitleaks_dir.json")
        assert parsed["summary"]["total_secrets"] == len(raw), (
            f"summary.total_secrets {parsed['summary']['total_secrets']} "
            f"!= raw finding count {len(raw)}"
        )


# ---------------------------------------------------------------------------
# Binary round-trip tests  (requires gitleaks)
# ---------------------------------------------------------------------------


_SECRET_CONTENT = "\n" * 9 + 'const aws_key = "AKIAZ3XYMWQ2LR7NVBPA";\n'


def _make_secret_repo(path: Path) -> Path:
    """Create a minimal git repo with an AWS key at config/aws.js line 10."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (path / "config").mkdir()
    (path / "config" / "aws.js").write_text(_SECRET_CONTENT)
    subprocess.run(
        ["git", "-C", str(path), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "Add config"],
        check=True,
        capture_output=True,
    )
    return path


@requires_gitleaks
class TestGitleaksBinaryRoundTrip:
    """Full chain: gitleaks binary → JSON → parser → ingestor → ChromaDB.

    These tests verify that the field mappings are not broken end-to-end.
    They require ``gitleaks`` in PATH and are skipped otherwise.
    """

    def test_dir_scan_roundtrip(self, project_env: dict, tmp_path: Path) -> None:
        """Dir-scan: every metadata field in ChromaDB matches gitleaks raw output."""
        repo = _make_secret_repo(tmp_path / "git_repo")
        out = tmp_path / "findings.json"
        subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                ".",
                "--no-git",
                "--report-format",
                "json",
                "--report-path",
                str(out),
            ],
            capture_output=True,
            cwd=str(repo),
        )
        assert out.exists(), "gitleaks produced no output file — no findings detected"
        raw = json.loads(out.read_text())
        assert len(raw) > 0, "Expected at least one finding from the synthetic repo"

        parsed = parse_gitleaks_json(out)
        result = _make_gitleaks_result(parsed)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="roundtrip"
        )

        all_docs = _get_all_docs(engine)
        assert len(all_docs["metadatas"]) == len(raw), (
            f"Ingested {len(all_docs['metadatas'])} docs, "
            f"gitleaks found {len(raw)} secrets"
        )
        meta = all_docs["metadatas"][0]
        assert meta["rule_id"] == raw[0]["RuleID"]
        assert meta["file_path"] == raw[0]["File"]
        assert meta["line_number"] == raw[0]["StartLine"]
        assert meta["tool"] == "gitleaks"
        assert meta["severity"] == "high"
        assert "commit" not in meta, "Dir scan should have no commit key in metadata"

    def test_git_scan_roundtrip(self, project_env: dict, tmp_path: Path) -> None:
        """Git-scan: commit hash from gitleaks is stored faithfully in ChromaDB."""
        repo = _make_secret_repo(tmp_path / "git_repo")
        out = tmp_path / "findings.json"
        subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                ".",
                "--report-format",
                "json",
                "--report-path",
                str(out),
            ],
            capture_output=True,
            cwd=str(repo),
        )
        assert out.exists(), "gitleaks produced no output file"
        raw = json.loads(out.read_text())
        assert len(raw) > 0, "Expected at least one finding from the synthetic repo"
        assert raw[0]["Commit"], "git scan must produce a non-empty Commit hash"

        parsed = parse_gitleaks_json(out)
        result = _make_gitleaks_result(parsed)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="roundtrip-git"
        )

        all_docs = _get_all_docs(engine)
        assert len(all_docs["metadatas"]) == len(raw)
        meta = all_docs["metadatas"][0]
        assert meta["rule_id"] == raw[0]["RuleID"]
        assert meta["file_path"] == raw[0]["File"]
        assert meta["line_number"] == raw[0]["StartLine"]
        assert meta["tool"] == "gitleaks"
        assert meta["severity"] == "high"
        assert "commit" in meta, "Git scan must store commit in metadata"
        assert meta["commit"] == raw[0]["Commit"]
