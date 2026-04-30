"""End-to-end tests for gitleaks chat with real binary."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from application.project import ProjectManager
from application.rag import RAGEngine
from application.rag.query import QueryEngine
from application.tools.executor import ToolExecutor
from application.tools.registry import discover_tools, tool_registry
from core.config import ConfigManager
from core.config.schemas import CommandEntry
from domain.tools.base import ToolResult
from tests.conftest import requires_gitleaks, requires_ollama
from web.adapters.no_approval_prompt import NoApprovalPromptAdapter

pytestmark = pytest.mark.e2e

_TALLY_ROOT = Path(__file__).resolve().parents[2]

slow = pytest.mark.slow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        project_name=project_name,
        base_path=base_path,
        prompt=NoApprovalPromptAdapter(),
    )
    return executor.execute(
        tool,
        repo_path=str(repo_path),
        scan_type=scan_type,
        label="test-repo",
    )


def _make_rag_engine(base_path: Path, project_name: str) -> RAGEngine:
    return RAGEngine(project_name=project_name, base_path=str(base_path))


def _run_pipeline(
    base_path: Path,
    project_name: str,
    result: ToolResult,
    profile: str,
    repo: str | None = None,
) -> list[int]:
    """Drive the full ingest pipeline; returns SQLite finding IDs."""
    from application.pipeline.factory import PipelineFactory
    from domain.pipeline.events import IngestCompleted, ToolCompleted

    bus = PipelineFactory.create()

    ids: list[int] = []

    def _capture(event: IngestCompleted) -> None:
        ids.extend(event.ids)

    bus.subscribe(IngestCompleted, _capture)
    bus.dispatch(
        ToolCompleted(result, profile, None, project_name, str(base_path), repo=repo)
    )
    return ids


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
    pm.create_project_dirs(name)
    pm.save_project(name)
    return {"base_path": tmp_path, "project_name": name}


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
        ids = _run_pipeline(base, name, result, profile="test-repo")
        assert len(ids) > 0, "pipeline produced 0 SQLite rows for gitleaks"
        engine = _make_rag_engine(base, name)
        try:
            assert engine.count_documents() == len(ids), (
                f"ChromaDB doc count {engine.count_documents()} "
                f"!= SQLite row count {len(ids)}"
            )
            response = QueryEngine(engine).chat("what secrets were found in the repo?")
        finally:
            engine.close()
        assert isinstance(response, str)
        assert len(response) > 0
