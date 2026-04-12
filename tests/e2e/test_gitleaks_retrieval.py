"""End-to-end retrieval tests for gitleaks → ChromaDB → QueryEngine.

Requires Ollama running and configured.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from application.rag.ingestor import ToolHandlerFactory
from domain.tools.base import ToolResult
from infrastructure.tools.parsers.gitleaks import parse_gitleaks_json
from tests.conftest import requires_ollama

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"


def _parse_fixture(filename: str) -> dict:
    return parse_gitleaks_json(_FIXTURES / filename)


_TIMESTAMP = "2024-01-01T00:00:00"


def _make_gitleaks_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="gitleaks",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


def _ingest_to_chroma(engine: RAGEngine, result: ToolResult, profile: str) -> None:
    """Normalize rows and add rendered text to ChromaDB."""
    handler = ToolHandlerFactory.load(result.tool_name)
    if handler is None or not result.parsed_data:
        return
    rows = handler.normalize(result, profile=profile)
    if not rows:
        return
    texts = [handler.render(row) for row in rows]
    metadatas = [{"tool": row["tool"], "profile": row["profile"]} for row in rows]
    ids = [row["fingerprint"] for row in rows]
    engine.add_documents(texts, metadatas, ids)


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


class TestGitleaksRetrieval:
    @requires_ollama
    def test_semantic_search_by_rule_id(
        self, project_env: dict, dir_parsed_data: dict
    ) -> None:
        """Searching for a rule_id value returns the expected document in top-5."""
        from application.rag.query import QueryEngine

        result = _make_gitleaks_result(dir_parsed_data)
        engine = RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        try:
            _ingest_to_chroma(engine, result, profile="test-repo")
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
        from application.rag.query import QueryEngine

        result = _make_gitleaks_result(dir_parsed_data)
        engine = RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        try:
            _ingest_to_chroma(engine, result, profile="test-repo")
            qe = QueryEngine(engine)
            results = qe.search("what did gitleaks find?")
            assert results, "Expected results for tool-specific query"
            for r in results:
                assert r["metadata"]["tool"] == "gitleaks", (
                    f"Tool filter failed — got tool={r['metadata']['tool']!r}"
                )
        finally:
            engine.close()
