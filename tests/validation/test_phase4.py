"""End-to-end validation tests for the Phase 4 nmap → RAG pipeline.

Run from the tally project root:
    pytest tests/validation/ -v

Skip markers:
    requires_nmap    — skipped when nmap binary is not installed
    requires_ollama  — skipped when Ollama is not reachable
    slow             — long-running tests (real nmap scans or sleep-based timing)
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest

# Ensure tally root is on sys.path when running pytest directly.
_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config import ConfigManager  # noqa: E402
from core.config.schemas import NmapProfile  # noqa: E402
from core.project import ProjectManager  # noqa: E402
from core.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.rag.engine import verify_ollama_available  # noqa: E402
from core.rag.query import QueryEngine  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402
from core.tools.executor import ToolExecutor  # noqa: E402
from core.tools.registry import tool_registry  # noqa: E402

# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

_OLLAMA_URL = "http://localhost:11434"

requires_nmap = pytest.mark.skipif(
    shutil.which("nmap") is None,
    reason="nmap not installed",
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
    """Minimal project environment under tmp_path (no nmap config, no data)."""
    name = "test-proj"
    _write_global_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm._create_project_dirs(name)
    pm._save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


@pytest.fixture()
def nmap_project_env(project_env: dict) -> dict:
    """project_env with a localhost nmap profile pre-configured."""
    _write_nmap_config(project_env["base_path"], project_env["project_name"])
    return project_env


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


def _write_nmap_config(base_path: Path, project_name: str) -> None:
    cm = ConfigManager(base_path=str(base_path))
    cm.save_nmap_hosts(
        project_name,
        {"localhost": NmapProfile(hosts=["127.0.0.1"], nmap_args="-p 22,80,443")},
    )


def _make_nmap_result() -> ToolResult:
    """Synthetic ToolResult with valid parsed nmap data. No nmap binary needed."""
    return ToolResult(
        tool_name="nmap",
        success=True,
        output="",
        parsed_data={
            "hosts": [
                {
                    "ip_address": "127.0.0.1",
                    "hostname": "localhost",
                    "state": "up",
                    "ports": [
                        {
                            "port": 22,
                            "protocol": "tcp",
                            "state": "open",
                            "service": "ssh",
                            "version": "",
                        },
                        {
                            "port": 80,
                            "protocol": "tcp",
                            "state": "open",
                            "service": "http",
                            "version": "",
                        },
                    ],
                }
            ]
        },
        output_files={},
        timestamp=RAGEngine.now_iso(),
        duration_seconds=0.1,
    )


def _run_scan(
    base_path: Path, project_name: str, profile: str = "localhost"
) -> ToolResult:
    tool = tool_registry.get_tool("nmap")
    assert tool is not None
    executor = ToolExecutor(
        project_name=project_name, base_path=base_path, auto_approve=True
    )
    return executor.execute(
        tool,
        label=profile,
        profile=profile,
        project_name=project_name,
        base_path=str(base_path),
    )


def _make_rag_engine(base_path: Path, project_name: str) -> RAGEngine:
    return RAGEngine(project_name=project_name, base_path=str(base_path))


def _ingest(
    base_path: Path, project_name: str, result: ToolResult, profile: str = "localhost"
) -> list[str]:
    engine = _make_rag_engine(base_path, project_name)
    return FindingIngestor(engine, project_name).ingest_tool_output(
        result, profile=profile
    )


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
# Scenario 2 – Nmap configuration  (no external deps)
# ---------------------------------------------------------------------------


class TestNmapConfig:
    def test_nmap_profile_round_trips(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _write_nmap_config(base, name)

        profiles = ConfigManager(base_path=str(base)).load_nmap_hosts(name)
        assert profiles is not None
        assert "localhost" in profiles
        assert "127.0.0.1" in profiles["localhost"].hosts
        assert "-p 22,80,443" in profiles["localhost"].nmap_args


# ---------------------------------------------------------------------------
# Scenario 3 – Nmap scan execution  (@requires_nmap @slow)
# ---------------------------------------------------------------------------


@requires_nmap
@slow
class TestNmapExecution:
    def test_scan_succeeds(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        assert result.success, f"Scan failed: {result.output}"

    def test_output_file_created(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        assert result.output_files
        stdout = result.output_files.get("stdout")
        assert stdout is not None and Path(stdout).exists()

    def test_output_file_is_xml(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        content = Path(result.output_files["stdout"]).read_text()
        assert content.lstrip().startswith("<?xml")

    def test_parsed_data_has_hosts(self, nmap_project_env: dict) -> None:
        result = _run_scan(
            nmap_project_env["base_path"], nmap_project_env["project_name"]
        )
        assert result.parsed_data is not None
        assert "error" not in result.parsed_data
        assert "hosts" in result.parsed_data


# ---------------------------------------------------------------------------
# Scenario 4a – Ingestion unit tests  (@requires_ollama, no nmap, not slow)
#
# Uses _make_nmap_result() so these run without nmap and in milliseconds.
# ---------------------------------------------------------------------------


@requires_ollama
class TestIngestionUnit:
    def test_ingestion_returns_positive_count(self, project_env: dict) -> None:
        count = _ingest(
            project_env["base_path"], project_env["project_name"], _make_nmap_result()
        )
        assert len(count) >= 1

    def test_stats_shows_nmap_documents(self, project_env: dict) -> None:
        _ingest(
            project_env["base_path"], project_env["project_name"], _make_nmap_result()
        )
        stats = _make_rag_engine(
            project_env["base_path"], project_env["project_name"]
        ).get_stats()
        assert stats["total_documents"] > 0
        assert "nmap" in stats["by_tool"]

    def test_failed_result_not_ingested(self, project_env: dict) -> None:
        failed = ToolResult(
            tool_name="nmap",
            success=False,
            output="denied",
            parsed_data=None,
            output_files={},
            timestamp=RAGEngine.now_iso(),
            duration_seconds=0.0,
        )
        count = _ingest(project_env["base_path"], project_env["project_name"], failed)
        assert count == []

    def test_parse_error_result_not_ingested(self, project_env: dict) -> None:
        errored = ToolResult(
            tool_name="nmap",
            success=True,
            output="",
            parsed_data={"error": "malformed XML"},
            output_files={},
            timestamp=RAGEngine.now_iso(),
            duration_seconds=0.0,
        )
        count = _ingest(project_env["base_path"], project_env["project_name"], errored)
        assert count == []


# ---------------------------------------------------------------------------
# Scenario 4b – delete_findings  (@requires_ollama, no nmap, not slow)
#
# This is the targeted test that would have caught the ChromaDB 1.x $and bug.
# It bypasses the ingestor and calls add_documents / delete_findings directly
# so timing of IDs is irrelevant and the behaviour is unambiguous.
# ---------------------------------------------------------------------------


@requires_ollama
class TestDeleteFindings:
    def _add_docs(self, engine: RAGEngine, profile: str, ids: list[str]) -> None:
        ts = RAGEngine.now_iso()
        engine.add_documents(
            texts=[f"Host 1.2.3.4 ({profile})" for _ in ids],
            metadatas=[
                {
                    "tool": "nmap",
                    "profile": profile,
                    "finding_type": "host",
                    "timestamp": ts,
                }
                for _ in ids
            ],
            ids=ids,
        )

    def test_delete_by_tool_and_profile(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "localhost", ["doc-a", "doc-b"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("nmap", "localhost")

        assert deleted == 2
        assert engine.count_documents() == 0

    def test_delete_scoped_to_profile_leaves_others(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "profile-a", ["a-1"])
        self._add_docs(engine, "profile-b", ["b-1"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("nmap", "profile-a")

        assert deleted == 1
        assert engine.count_documents() == 1

    def test_delete_by_tool_only_removes_all_profiles(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        self._add_docs(engine, "profile-a", ["a-1"])
        self._add_docs(engine, "profile-b", ["b-1"])
        assert engine.count_documents() == 2

        deleted = engine.delete_findings("nmap")

        assert deleted == 2
        assert engine.count_documents() == 0

    def test_delete_nonexistent_returns_zero(self, project_env: dict) -> None:
        engine = _make_rag_engine(project_env["base_path"], project_env["project_name"])
        assert engine.count_documents() == 0

        deleted = engine.delete_findings("nmap", "localhost")

        assert deleted == 0


# ---------------------------------------------------------------------------
# Scenario 5a – Search unit  (@requires_ollama, no nmap, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestSearchUnit:
    def test_search_empty_collection_returns_empty(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        assert qe.search("anything") == []

    def test_search_blank_query_returns_empty(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        assert qe.search("   ") == []

    def test_search_results_have_required_keys(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_nmap_result())
        results = QueryEngine(_make_rag_engine(base, name)).search("127.0.0.1")
        assert len(results) > 0
        for r in results:
            assert "document" in r
            assert "metadata" in r
            assert "distance" in r

    def test_search_results_sorted_by_distance(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_nmap_result())
        results = QueryEngine(_make_rag_engine(base, name)).search("host port open")
        distances = [r["distance"] for r in results]
        assert distances == sorted(distances)


# ---------------------------------------------------------------------------
# Scenario 5b – Search e2e with real nmap  (@requires_nmap @requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_nmap
@requires_ollama
@slow
class TestSearchE2E:
    def test_search_returns_results_from_real_scan(
        self, nmap_project_env: dict
    ) -> None:
        base, name = nmap_project_env["base_path"], nmap_project_env["project_name"]
        result = _run_scan(base, name)
        _ingest(base, name, result)
        results = QueryEngine(_make_rag_engine(base, name)).search(
            "127.0.0.1", n_results=5
        )
        assert len(results) > 0


# ---------------------------------------------------------------------------
# Scenario 6a – Chat unit  (@requires_ollama, no nmap, not slow)
# ---------------------------------------------------------------------------


@requires_ollama
class TestChatUnit:
    def test_chat_no_data_returns_informative_message(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        response = qe.chat("what hosts were scanned?")
        assert isinstance(response, str)
        assert "No relevant findings" in response

    def test_chat_blank_message_returns_prompt(self, project_env: dict) -> None:
        qe = QueryEngine(
            _make_rag_engine(project_env["base_path"], project_env["project_name"])
        )
        assert "Please provide a message" in qe.chat("   ")

    def test_chat_with_data_returns_non_empty_string(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]
        _ingest(base, name, _make_nmap_result())
        response = QueryEngine(_make_rag_engine(base, name)).chat(
            "what ports are open?"
        )
        assert isinstance(response, str)
        assert len(response) > 0


# ---------------------------------------------------------------------------
# Scenario 6b – Chat e2e with real nmap  (@requires_nmap @requires_ollama @slow)
# ---------------------------------------------------------------------------


@requires_nmap
@requires_ollama
@slow
class TestChatE2E:
    def test_chat_references_scan_data(self, nmap_project_env: dict) -> None:
        base, name = nmap_project_env["base_path"], nmap_project_env["project_name"]
        result = _run_scan(base, name)
        _ingest(base, name, result)
        response = QueryEngine(_make_rag_engine(base, name)).chat(
            "what hosts were scanned?"
        )
        assert isinstance(response, str)
        assert len(response) > 0


# ---------------------------------------------------------------------------
# Scenario 7 – Upsert / no duplicates on re-ingest  (@requires_ollama @slow)
#
# Uses _make_nmap_result() (no nmap needed).  time.sleep(1) forces the
# second ingestion to produce different document IDs (ts_compact is
# second-granularity), so deduplication depends entirely on delete_findings
# rather than upsert coincidentally matching identical IDs.
# ---------------------------------------------------------------------------


@requires_ollama
@slow
class TestUpsert:
    def test_rescan_does_not_duplicate_documents(self, project_env: dict) -> None:
        base, name = project_env["base_path"], project_env["project_name"]

        count1 = _ingest(base, name, _make_nmap_result())
        assert len(count1) >= 1
        total_after_first = _make_rag_engine(base, name).count_documents()

        time.sleep(1)  # force different ts_compact → different IDs in second ingest

        _ingest(base, name, _make_nmap_result())
        total_after_second = _make_rag_engine(base, name).count_documents()

        assert total_after_second == total_after_first, (
            f"Document count grew {total_after_first} → {total_after_second}: "
            "delete_findings is not clearing stale docs before re-ingestion"
        )


# ---------------------------------------------------------------------------
# Scenario 8 – Project isolation  (@requires_ollama)
# ---------------------------------------------------------------------------


@requires_ollama
class TestProjectIsolation:
    def _make_two_projects(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        pm = ProjectManager(base_path=str(tmp_path))
        for n in ("proj-a", "proj-b"):
            pm._create_project_dirs(n)
            pm._save_project(n, [])

    def test_new_project_starts_empty(self, tmp_path: Path) -> None:
        self._make_two_projects(tmp_path)
        engine_a = RAGEngine(project_name="proj-a", base_path=str(tmp_path))
        engine_b = RAGEngine(project_name="proj-b", base_path=str(tmp_path))
        assert engine_a.collection_name != engine_b.collection_name
        assert engine_b.count_documents() == 0

    def test_ingest_does_not_leak_to_other_project(self, tmp_path: Path) -> None:
        self._make_two_projects(tmp_path)
        count = _ingest(tmp_path, "proj-a", _make_nmap_result())
        assert len(count) >= 1
        assert (
            RAGEngine(project_name="proj-b", base_path=str(tmp_path)).count_documents()
            == 0
        )
