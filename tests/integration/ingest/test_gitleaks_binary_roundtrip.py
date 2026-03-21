"""Integration tests for gitleaks binary round-trip (requires gitleaks binary)."""

from __future__ import annotations

import json
import shutil
import subprocess
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
from tests.conftest import requires_gitleaks  # noqa: E402

pytestmark = pytest.mark.integration

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


@requires_gitleaks
class TestGitleaksBinaryRoundTrip:
    """Full chain: gitleaks binary → JSON → parser → ingestor → ChromaDB.

    These tests verify that the field mappings are not broken end-to-end.
    They require ``gitleaks`` in PATH and are skipped otherwise.
    """

    def test_dir_scan_roundtrip(self, project_env: dict, tmp_path: Path) -> None:
        """Dir-scan: every metadata field in ChromaDB matches gitleaks output."""
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
