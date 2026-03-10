"""End-to-end validation tests for the gitleaks → RAG pipeline.

Run from the tally project root:
    pytest tests/validation/test_gitleaks_rag_ingest.py -v

Skip markers:
    requires_gitleaks — skipped when gitleaks binary is not installed
    requires_ollama   — skipped when Ollama is not reachable
    slow              — long-running tests (real gitleaks scans or sleep-based timing)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Ensure tally root is on sys.path when running pytest directly.
_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config import ConfigManager  # noqa: E402
from core.config.schemas import CommandEntry  # noqa: E402
from core.project import ProjectManager  # noqa: E402
from core.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.rag.engine import verify_ollama_available  # noqa: E402
from core.rag.query import QueryEngine  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402
from core.tools.executor import ToolExecutor  # noqa: E402
from core.tools.registry import discover_tools, tool_registry  # noqa: E402

# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

_OLLAMA_URL = "http://localhost:11434"

requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks not installed",
)
requires_ollama = pytest.mark.skipif(
    not verify_ollama_available(_OLLAMA_URL),
    reason="Ollama not running at http://localhost:11434",
)
slow = pytest.mark.slow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    """Minimal project environment under tmp_path (no data)."""
    name = "test-gitleaks-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm._create_project_dirs(name)
    pm._save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_global_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama_base_url": "http://localhost:11434",
                "default_llm": "qwen3:14b",
                "default_embedding": "nomic-embed-text:latest",
            }
        )
    )


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
        timestamp=RAGEngine.now_iso(),
        duration_seconds=0.1,
    )


def _init_test_repo(tmp_path: Path) -> Path:
    """Create a git repo with a committed fake AWS key. Returns repo path."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    secret_file = repo / "config.js"
    secret_file.write_text('const key = "AKIAXYZ3FGHLMN2PQRST";\n')
    subprocess.run(
        ["git", "-C", str(repo), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "add config"],
        check=True,
        capture_output=True,
    )
    return repo


def _run_scan(
    base_path: Path,
    project_name: str,
    repo_path: Path,
    scan_type: str = "dir",
) -> ToolResult:
    discover_tools(str(base_path))
    tool = tool_registry.get_tool("gitleaks")
    assert tool is not None, "gitleaks not registered after discover_tools"
    executor = ToolExecutor(
        project_name=project_name, base_path=base_path, auto_approve=True
    )
    return executor.execute(
        tool,
        repo_path=str(repo_path),
        scan_type=scan_type,
        label="test-repo",
    )


def _make_rag_engine(base_path: Path, project_name: str) -> RAGEngine:
    return RAGEngine(project_name=project_name, base_path=str(base_path))


def _ingest(
    base_path: Path,
    project_name: str,
    result: ToolResult,
    profile: str = "my-test-repo",
) -> list[str]:
    engine = _make_rag_engine(base_path, project_name)
    try:
        return FindingIngestor(engine, project_name).ingest_tool_output(
            result, profile=profile
        )
    finally:
        engine.close()


# ---------------------------------------------------------------------------
# Scenario 1 – Project creation  (no external deps)
# ---------------------------------------------------------------------------


class TestProjectCreation:
    def test_project_dirs_created(self, project_env: dict) -> None:
        root = project_env["base_path"] / "projects" / project_env["project_name"]
        expected = [
            root / "config" / "endpoints",
            root / "chroma_db",
            root / "tool_outputs" / "nmap",
            root / "tool_outputs" / "semgrep",
            root / "tool_outputs" / "osv-scanner",
            root / "tool_outputs" / "gitleaks",
            root / "tool_outputs" / "zap",
            root / "sessions",
        ]
        for d in expected:
            assert d.is_dir(), f"Missing: {d}"

    def test_project_config_written(self, project_env: dict) -> None:
        p = (
            project_env["base_path"]
            / "projects"
            / project_env["project_name"]
            / "config"
            / "project.json"
        )
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["project_name"] == project_env["project_name"]
        assert "created" in data

    def test_nmap_hosts_initialised_empty(self, project_env: dict) -> None:
        p = (
            project_env["base_path"]
            / "projects"
            / project_env["project_name"]
            / "config"
            / "nmap_hosts.json"
        )
        assert p.exists()
        assert json.loads(p.read_text()) == {}

    def test_project_listed_by_manager(self, project_env: dict) -> None:
        pm = ProjectManager(base_path=str(project_env["base_path"]))
        assert project_env["project_name"] in pm.list_projects()


# ---------------------------------------------------------------------------
# Scenario 2 – commands.json round-trip  (no external deps)
# ---------------------------------------------------------------------------


class TestGitleaksCommandsConfig:
    def test_commands_config_round_trips(self, project_env: dict) -> None:
        base = project_env["base_path"]
        loaded = ConfigManager(base_path=str(base)).load_commands_config()
        assert loaded is not None
        assert "gitleaks" in loaded
        assert loaded["gitleaks"].type == "repo"
        assert loaded["gitleaks"].location == "local"


# ---------------------------------------------------------------------------
# Scenario 3 – Gitleaks scan execution  (@requires_gitleaks @slow)
# ---------------------------------------------------------------------------


@requires_gitleaks
@slow
class TestGitleaksExecution:
    def test_scan_succeeds(self, project_env: dict, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = _run_scan(project_env["base_path"], project_env["project_name"], repo)
        assert result.success, f"Scan failed: {result.output}"

    def test_parsed_data_has_secrets(self, project_env: dict, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = _run_scan(project_env["base_path"], project_env["project_name"], repo)
        assert result.parsed_data is not None
        assert "secrets" in result.parsed_data

    def test_detected_secret_is_aws_key(
        self, project_env: dict, tmp_path: Path
    ) -> None:
        repo = _init_test_repo(tmp_path)
        result = _run_scan(project_env["base_path"], project_env["project_name"], repo)
        assert result.parsed_data is not None
        secrets = result.parsed_data.get("secrets", [])
        assert len(secrets) > 0
        rule_ids = [s.get("rule_id", "") for s in secrets]
        assert any("aws" in rid.lower() for rid in rule_ids), (
            f"Expected an aws rule_id, got: {rule_ids}"
        )


# ---------------------------------------------------------------------------
# Scenario 4a – Ingestion unit tests  (@requires_ollama, no gitleaks, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestIngestionUnit:
    def test_ingestion_returns_positive_count(self, project_env: dict) -> None:
        ids = _ingest(
            project_env["base_path"],
            project_env["project_name"],
            _make_gitleaks_result(),
        )
        assert len(ids) >= 1

    def test_stats_shows_gitleaks_documents(self, project_env: dict) -> None:
        _ingest(
            project_env["base_path"],
            project_env["project_name"],
            _make_gitleaks_result(),
        )
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            stats = engine.get_stats()
        finally:
            engine.close()
        assert stats["total_documents"] > 0
        assert "gitleaks" in stats["by_tool"]

    def test_failed_result_not_ingested(self, project_env: dict) -> None:
        failed = ToolResult(
            tool_name="gitleaks",
            success=False,
            output="permission denied",
            parsed_data=None,
            output_files={},
            timestamp=RAGEngine.now_iso(),
            duration_seconds=0.0,
        )
        ids = _ingest(project_env["base_path"], project_env["project_name"], failed)
        assert ids == []

    def test_empty_secrets_not_ingested(self, project_env: dict) -> None:
        empty = ToolResult(
            tool_name="gitleaks",
            success=True,
            output="",
            parsed_data={"secrets": [], "summary": {"total_secrets": 0}},
            output_files={},
            timestamp=RAGEngine.now_iso(),
            duration_seconds=0.0,
        )
        ids = _ingest(project_env["base_path"], project_env["project_name"], empty)
        assert ids == []

    def test_secret_value_not_in_document_text(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            results = QueryEngine(engine).search("aws-access-token")
        finally:
            engine.close()
        for r in results:
            assert "AKIAXYZ3FGHLMN2PQRST" not in r["document"], (
                "Secret value must not appear in stored document text"
            )


# ---------------------------------------------------------------------------
# Scenario 4b – delete_findings  (@requires_ollama, no gitleaks, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestDeleteFindings:
    def _add_docs(self, engine: RAGEngine, profile: str, ids: list[str]) -> None:
        ts = RAGEngine.now_iso()
        engine.add_documents(
            texts=[f"Secret in repo ({profile})" for _ in ids],
            metadatas=[
                {
                    "tool": "gitleaks",
                    "profile": profile,
                    "finding_type": "secret",
                    "timestamp": ts,
                }
                for _ in ids
            ],
            ids=ids,
        )

    def test_delete_by_tool_and_profile(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "my-repo", ["doc-a", "doc-b"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("gitleaks", "my-repo")

        assert deleted == 2
        assert engine.count_documents() == 0

    def test_delete_scoped_to_profile_leaves_others(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "repo-a", ["a-1"])
        self._add_docs(engine, "repo-b", ["b-1"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("gitleaks", "repo-a")

        assert deleted == 1
        assert engine.count_documents() == 1

    def test_delete_by_tool_only_removes_all_profiles(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "repo-a", ["a-1"])
        self._add_docs(engine, "repo-b", ["b-1"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("gitleaks")

        assert deleted == 2
        assert engine.count_documents() == 0

    def test_delete_nonexistent_returns_zero(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        assert engine.count_documents() == 0

        deleted = engine.delete_findings("gitleaks", "my-repo")

        assert deleted == 0


# ---------------------------------------------------------------------------
# Scenario 5a – Search unit  (@requires_ollama, no gitleaks, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestSearchUnit:
    def test_search_empty_collection_returns_empty(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            assert QueryEngine(engine).search("anything") == []
        finally:
            engine.close()

    def test_search_blank_query_returns_empty(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            assert QueryEngine(engine).search("   ") == []
        finally:
            engine.close()

    def test_search_results_have_required_keys(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            results = QueryEngine(engine).search("aws-access-token")
        finally:
            engine.close()
        assert len(results) > 0
        for r in results:
            assert "document" in r
            assert "metadata" in r
            assert "distance" in r

    def test_search_results_sorted_by_distance(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            results = QueryEngine(engine).search("secret detected")
        finally:
            engine.close()
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances)

    def test_tool_filter_fires_for_gitleaks_query(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            results = QueryEngine(engine).search("what did gitleaks find?")
        finally:
            engine.close()
        assert len(results) > 0
        for r in results:
            assert r["metadata"]["tool"] == "gitleaks", (
                f"Expected tool=gitleaks, got {r['metadata']['tool']}"
            )


# ---------------------------------------------------------------------------
# Scenario 5b – Search e2e with real gitleaks  (@requires_gitleaks @requires_ollama)
# ---------------------------------------------------------------------------


@requires_gitleaks
@requires_ollama
@slow
class TestSearchE2E:
    def test_search_returns_results_from_real_scan(
        self, project_env: dict, tmp_path: Path
    ) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        repo = _init_test_repo(tmp_path)
        result = _run_scan(base, name, repo)
        _ingest(base, name, result)
        engine = _make_rag_engine(base, name)
        try:
            results = QueryEngine(engine).search("aws secret", n_results=5)
        finally:
            engine.close()
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Scenario 6a – Chat unit  (@requires_ollama, no gitleaks, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestChatUnit:
    def test_chat_no_data_returns_informative_message(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            response = QueryEngine(engine).chat("what secrets were found?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert "No relevant findings" in response

    def test_chat_blank_message_returns_prompt(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        try:
            response = QueryEngine(engine).chat("   ")
        finally:
            engine.close()
        assert "Please provide a message" in response

    def test_chat_with_data_returns_non_empty_string(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            response = QueryEngine(engine).chat("what secrets were detected?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert len(response) > 0


# ---------------------------------------------------------------------------
# Scenario 6b – Chat e2e with real gitleaks  (@requires_gitleaks @requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_gitleaks
@requires_ollama
@slow
class TestChatE2E:
    def test_chat_references_scan_data(self, project_env: dict, tmp_path: Path) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        repo = _init_test_repo(tmp_path)
        result = _run_scan(base, name, repo)
        _ingest(base, name, result)
        engine = _make_rag_engine(base, name)
        try:
            response = QueryEngine(engine).chat("what secrets were found in the repo?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert len(response) > 0


# ---------------------------------------------------------------------------
# Scenario 7 – Upsert / no duplicates on re-ingest  (@requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_ollama
@slow
class TestUpsert:
    def test_rescan_does_not_duplicate_documents(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]

        ids1 = _ingest(base, name, _make_gitleaks_result())
        assert len(ids1) >= 1
        engine = _make_rag_engine(base, name)
        try:
            count_after_first = engine.count_documents()
        finally:
            engine.close()

        time.sleep(1)  # force different ts_compact → different IDs in second ingest

        _ingest(base, name, _make_gitleaks_result())
        engine = _make_rag_engine(base, name)
        try:
            count_after_second = engine.count_documents()
        finally:
            engine.close()

        assert count_after_second == count_after_first, (
            f"Document count grew {count_after_first} → {count_after_second}: "
            "delete_findings is not clearing stale docs before re-ingestion"
        )


# ---------------------------------------------------------------------------
# Scenario 8 – Project isolation  (@requires_ollama)
# ---------------------------------------------------------------------------


@requires_ollama
class TestProjectIsolation:
    def _make_two_projects(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        _write_commands_config(tmp_path)
        pm = ProjectManager(base_path=str(tmp_path))
        for n in ("proj-a", "proj-b"):
            pm._create_project_dirs(n)
            pm._save_project(n, [])

    def test_new_project_starts_empty(self, tmp_path: Path) -> None:
        self._make_two_projects(tmp_path)
        engine_a = RAGEngine(project_name="proj-a", base_path=str(tmp_path))
        engine_b = RAGEngine(project_name="proj-b", base_path=str(tmp_path))
        try:
            assert engine_a.collection_name != engine_b.collection_name
            assert engine_b.count_documents() == 0
        finally:
            engine_a.close()
            engine_b.close()

    def test_ingest_does_not_leak_to_other_project(self, tmp_path: Path) -> None:
        self._make_two_projects(tmp_path)
        ids = _ingest(tmp_path, "proj-a", _make_gitleaks_result())
        assert len(ids) >= 1
        engine_b = RAGEngine(project_name="proj-b", base_path=str(tmp_path))
        try:
            assert engine_b.count_documents() == 0
        finally:
            engine_b.close()
