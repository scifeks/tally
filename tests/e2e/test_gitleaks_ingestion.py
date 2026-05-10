"""End-to-end tests for gitleaks ingestion (unit, no binary required)."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from application.project import ProjectManager
from application.rag.ingestor import ToolHandlerFactory
from application.rag.knowledge_base import FindingKnowledgeBase
from application.rag.query import QueryEngine
from core.config import ConfigManager
from core.config.schemas import CommandEntry
from domain.tools.base import ToolResult
from infrastructure.embedding.factory import get_embedding_provider
from infrastructure.llm.factory import get_llm_provider
from infrastructure.vector.factory import make_chromadb_vector_index
from tests.conftest import requires_ollama

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]
_TIMESTAMP = "2024-01-01T00:00:00"


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _write_commands_config(base_path: Path) -> None:
    cm = ConfigManager(base_path=str(base_path))
    cm.save_commands_config(
        {
            "gitleaks": CommandEntry(
                type="repo",
                location="local",
                path=shutil.which("gitleaks") or "/usr/local/bin/gitleaks",
            ),
            "nmap": CommandEntry(
                type="repo",
                location="local",
                path=shutil.which("nmap") or "/usr/bin/nmap",
            ),
        }
    )


def _make_gitleaks_result() -> ToolResult:
    """Synthetic single-secret ToolResult. No gitleaks binary needed."""
    return ToolResult(
        tool_name="gitleaks",
        success=True,
        output="",
        parsed_data={
            "secrets": [
                {
                    "rule_id": "aws-access-token",
                    "description": "AWS Access Token",
                    "file_path": "config/aws.js",
                    "line_number": 10,
                    "commit": "",
                    "tags": [],
                    "fingerprint": "config/aws.js:aws-access-token:10",
                    "secret": "AKIAXYZ3FGHLMN2PQRST",
                    "match": "AKIAXYZ3FGHLMN2PQRST",
                }
            ],
            "summary": {
                "total_secrets": 1,
                "by_rule": {"aws-access-token": 1},
                "files_with_secrets": 1,
            },
        },
        output_files={},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


def _make_kb(base_path: Path, project_name: str) -> FindingKnowledgeBase:
    embedding_provider = get_embedding_provider(base_path)
    chat_provider = get_llm_provider("chat", base_path)
    vector_index = make_chromadb_vector_index(
        project_name=project_name,
        base_path=base_path,
        embedding_provider=embedding_provider,
    )
    return FindingKnowledgeBase(
        vector_index=vector_index,
        chat_provider=chat_provider,
        project_name=project_name,
        base_path=base_path,
    )


def _ingest(
    base_path: Path,
    project_name: str,
    result: ToolResult,
    profile: str = "my-test-repo",
) -> list[dict]:
    """Normalize rows and embed rendered text into ChromaDB via Ollama."""
    if not result.success or not result.parsed_data:
        return []
    handler = ToolHandlerFactory.load(result.tool_name)
    if handler is None:
        return []
    rows = handler.normalize(result, profile=profile)
    if not rows:
        return []
    kb = _make_kb(base_path, project_name)
    try:
        texts = [handler.render(row) for row in rows]
        metadatas: list[Mapping[str, Any]] = [
            {"tool": row["tool"], "profile": row["profile"]} for row in rows
        ]
        ids = [row["fingerprint"] for row in rows]
        kb.add_findings(documents=texts, metadatas=metadatas, ids=ids)
    finally:
        kb.close()
    return rows


# Fixtures


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    """Minimal project environment under tmp_path (no data)."""
    name = "test-gitleaks-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name)
    return {"base_path": tmp_path, "project_name": name}


# Scenario 4a – Ingestion unit tests  (@requires_ollama, no gitleaks, not slow)


@requires_ollama
class TestIngestionUnit:
    def test_ingestion_returns_positive_count(self, project_env: dict) -> None:
        rows = _ingest(
            project_env["base_path"],
            project_env["project_name"],
            _make_gitleaks_result(),
        )
        assert len(rows) >= 1

    def test_stats_shows_gitleaks_documents(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        kb = _make_kb(base, name)
        try:
            stats = kb.compute_stats()
        finally:
            kb.close()
        assert stats.total_documents > 0
        assert "gitleaks" in stats.by_tool

    def test_failed_result_not_ingested(self, project_env: dict) -> None:
        failed = ToolResult(
            tool_name="gitleaks",
            success=False,
            output="permission denied",
            parsed_data=None,
            output_files={},
            timestamp=_TIMESTAMP,
            duration_seconds=0.0,
        )
        rows = _ingest(project_env["base_path"], project_env["project_name"], failed)
        assert rows == []

    def test_empty_secrets_not_ingested(self, project_env: dict) -> None:
        empty = ToolResult(
            tool_name="gitleaks",
            success=True,
            output="",
            parsed_data={"secrets": [], "summary": {"total_secrets": 0}},
            output_files={},
            timestamp=_TIMESTAMP,
            duration_seconds=0.0,
        )
        rows = _ingest(project_env["base_path"], project_env["project_name"], empty)
        assert rows == []

    def test_secret_value_not_in_document_text(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        kb = _make_kb(base, name)
        try:
            results = QueryEngine(kb).search("aws-access-token")
        finally:
            kb.close()
        for r in results:
            doc = r["document"]
            assert doc is not None
            assert "AKIAXYZ3FGHLMN2PQRST" not in doc, (
                "Secret value must not appear in stored document text"
            )
