"""Integration tests for the semgrep → ChromaDB ingestion pipeline.

Run from the tally project root:
    pytest tests/ingest/test_semgrep.py -v
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

from core.config.schemas import Repository  # noqa: E402
from core.project import ProjectManager  # noqa: E402
from core.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402
from core.tools.interface import ExecutionContext  # noqa: E402
from core.tools.wrappers.local.semgrep import SemgrepLocalTool  # noqa: E402

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_semgrep_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="semgrep",
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
                "semgrep": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/semgrep",
                },
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/gitleaks",
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
def findings_parsed_data() -> dict:
    raw = json.loads((_FIXTURES / "semgrep_findings.json").read_text())
    findings = []
    for f in raw["findings"]:
        entry: dict = {
            "rule_id": f["rule_id"],
            "severity": f["severity"],
            "message": f["message"],
            "file_path": f["file_path"],
            "line_start": f["line_start"],
            "line_end": f["line_end"],
            "code_snippet": f["code_snippet"],
            "cwe": f.get("cwe"),
            "owasp": f.get("owasp"),
        }
        findings.append(entry)
    return {"findings": findings, "summary": raw["summary"]}


# ---------------------------------------------------------------------------
# Ingestor tests
# ---------------------------------------------------------------------------


class TestSemgrepIngestor:
    def test_chunk_count(self, project_env: dict, findings_parsed_data: dict) -> None:
        """2 findings in fixture → 2 documents ingested."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert len(doc_ids) == 2
        assert engine.count_documents() == 2

    def test_shared_metadata(
        self, project_env: dict, findings_parsed_data: dict
    ) -> None:
        """Semgrep chunks have correct domain/enriched/type_* fields."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            assert meta["domain"] == "code"
            assert meta["enriched"] is False
            assert meta["type_vulnerability"] is True
            assert meta["type_weakness"] is True
            assert meta["type_secret"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_exposure"] is False
            assert meta["type_dependency"] is False

    def test_metadata_fidelity(
        self, project_env: dict, findings_parsed_data: dict
    ) -> None:
        """Metadata fields match the fixture data."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        assert len(all_docs["metadatas"]) == 2
        by_rule = {m["rule_id"]: m for m in all_docs["metadatas"]}
        fixture_by_rule = {f["rule_id"]: f for f in findings_parsed_data["findings"]}
        for rule_id, meta in by_rule.items():
            finding = fixture_by_rule[rule_id]
            assert meta["tool"] == "semgrep"
            assert meta["profile"] == "test-repo"
            assert meta["finding_type"] == '["vulnerability"]'
            assert meta["file_path"] == finding["file_path"]
            assert meta["line_start"] == finding["line_start"]
            assert meta["line_end"] == finding["line_end"]
            assert isinstance(meta["line_start"], int)
            assert isinstance(meta["line_end"], int)
            assert meta["severity"] == finding["severity"]

    def test_optional_cwe_owasp_present(
        self, project_env: dict, findings_parsed_data: dict
    ) -> None:
        """First finding has cwe and owasp in metadata."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        xss_metas = [
            m
            for m in all_docs["metadatas"]
            if m["rule_id"] == "python.flask.security.xss.reflected-xss-taint"
        ]
        assert len(xss_metas) == 1
        meta = xss_metas[0]
        assert "cwe" in meta
        assert meta["cwe"] == "CWE-79"
        assert "owasp" in meta
        assert meta["owasp"] == "A03:2021"

    def test_optional_cwe_owasp_absent(
        self, project_env: dict, findings_parsed_data: dict
    ) -> None:
        """Second finding (null cwe/owasp) has neither key in metadata."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        pw_metas = [
            m
            for m in all_docs["metadatas"]
            if m["rule_id"] == "python.lang.security.audit.hardcoded-password"
        ]
        assert len(pw_metas) == 1
        meta = pw_metas[0]
        assert "cwe" not in meta
        assert "owasp" not in meta

    def test_no_none_or_empty_metadata_values(
        self, project_env: dict, findings_parsed_data: dict
    ) -> None:
        """No metadata value is None or empty string."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-repo"
        )
        all_docs = _get_all_docs(engine)
        for meta in all_docs["metadatas"]:
            for key, val in meta.items():
                assert val is not None, f"None value for key {key!r}"
                if key != "source_file":
                    assert val != "", f"Empty string for key {key!r}"

    def test_return_type_is_list(
        self, project_env: dict, findings_parsed_data: dict
    ) -> None:
        """ingest_tool_output returns list[str] with correct length."""
        result = _make_semgrep_result(findings_parsed_data)
        engine = _make_rag_engine(project_env)
        doc_ids = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-repo")
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == 2
        assert all(isinstance(i, str) for i in doc_ids)


# ---------------------------------------------------------------------------
# build_execution_passes tests
# ---------------------------------------------------------------------------


def _make_repo(path: str, test_dirs: list[str]) -> Repository:
    return Repository.model_construct(
        name="test-repo",
        type=["api"],
        path=path,
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=test_dirs,
    )


def _make_context(repo: Repository) -> ExecutionContext:
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.get_repo_path.return_value = repo.path or "/repo"
    config_manager = MagicMock()
    return ExecutionContext(
        project_name="test",
        base_path="/tmp",
        repo=repo,
        config_manager=config_manager,
        registry=registry,
        is_docker=False,
    )


class TestSemgrepBuildExecutionPasses:
    def test_passes_exclude_from_test_dirs(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(str(repo_dir), ["tests", "spec"])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].kwargs["exclude"] == ["tests", "spec"]

    def test_no_exclude_when_empty_and_no_auto_detect(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        # no test subdirs in repo_dir
        repo = _make_repo(str(repo_dir), [])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert "exclude" not in passes[0].kwargs

    def test_auto_detects_exclude_when_test_dirs_empty(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "tests").mkdir()
        repo = _make_repo(str(repo_dir), [])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].kwargs["exclude"] == ["tests"]
