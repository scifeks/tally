"""Integration tests for gitleaks combined-scan → ChromaDB ingestion."""

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
    combine_gitleaks_results,
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


@pytest.fixture()
def git_parsed_data() -> dict:
    return _parse_fixture("gitleaks_git.json")


@pytest.fixture()
def combined_parsed_data(dir_parsed_data: dict, git_parsed_data: dict) -> dict:
    return combine_gitleaks_results(dir_parsed_data, git_parsed_data)


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
        self,
        project_env: dict,
        dir_parsed_data: dict,
        git_parsed_data: dict,
    ) -> None:
        """The shared finding appears exactly once after combine."""
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
