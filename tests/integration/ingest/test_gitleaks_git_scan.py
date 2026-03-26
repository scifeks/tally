"""Integration tests for gitleaks git-scan → ChromaDB ingestion."""

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
def git_parsed_data() -> dict:
    return _parse_fixture("gitleaks_git.json")


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
                f"[gitleaks] Rule: {rule_id} | File: {file_path}:{line_number}"
            ) in text

        import json as _json

        raw_fixture = _json.load(open(_FIXTURES / "gitleaks_git.json"))
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
