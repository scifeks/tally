"""Tests for mcp.orchestrator."""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from mcp.orchestrator import run_triage  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT,
    triaged_at TEXT,
    triaged_by TEXT
);
CREATE TABLE IF NOT EXISTS tool_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    arguments TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    duration_ms INTEGER,
    called_at TEXT NOT NULL
);
"""


def _make_db(db_path: Path, rows: list[tuple[str]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    for (tool,) in rows:
        conn.execute(
            "INSERT INTO findings (tool, triaged_at) VALUES (?, NULL)", (tool,)
        )
    conn.commit()
    conn.close()


def _insert_audit_row(db_path: Path, tool_name: str, called_at: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO tool_audit_log (tool_name, arguments, success, called_at) "
        "VALUES (?, '{}', 1, ?)",
        (tool_name, called_at),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_db(tmp_path: Path):
    """Create a minimal project DB and patch _APP_ROOT."""
    project = "test-project"
    db = tmp_path / "projects" / project / "sqlite" / "findings.db"
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    return project, tmp_path, db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_skip_tools(project_db, caplog) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("nmap",), ("tree-sitter",)])

    import mcp.orchestrator as orch

    with patch.object(orch, "_APP_ROOT", tmp_root):
        result = (
            run_triage.__wrapped__(project)
            if hasattr(run_triage, "__wrapped__")
            else _run_with_root(orch, project, tmp_root)
        )

    assert result["sessions_run"] == 0
    assert result["success"] == 0
    assert result["failed"] == 0
    assert result["incomplete"] == 0


def _run_with_root(orch_mod, project: str, tmp_root: Path) -> dict:
    """Invoke run_triage with _APP_ROOT patched."""
    with patch.object(orch_mod, "_APP_ROOT", tmp_root):
        return orch_mod.run_triage(project)


def test_mcp_json_written(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("semgrep",)])  # non-skip tool so a session runs

    import json

    import mcp.orchestrator as orch

    captured: dict = {}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    def fake_run(*args, **kwargs):
        mcp_json = tmp_root / ".mcp.json"
        captured["exists"] = mcp_json.exists()
        if mcp_json.exists():
            captured["data"] = json.loads(mcp_json.read_text())
        return mock_result

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("subprocess.run", side_effect=fake_run),
    ):
        orch.run_triage(project)

    assert captured.get("exists") is True
    assert project in str(captured.get("data", {}))


def test_success_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("semgrep",)])

    import mcp.orchestrator as orch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    session_start_holder: list[str] = []

    def fake_run(*args, **kwargs):
        # Insert an audit row so the session is "success"
        ts = datetime.now(UTC).isoformat()
        session_start_holder.append(ts)
        _insert_audit_row(db, "update_finding", ts)
        return mock_result

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("subprocess.run", side_effect=fake_run),
    ):
        result = orch.run_triage(project)

    assert result["sessions_run"] == 1
    assert result["success"] == 1
    assert result["failed"] == 0
    assert result["incomplete"] == 0


def test_incomplete_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("semgrep",)])

    import mcp.orchestrator as orch

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("subprocess.run", return_value=mock_result),
    ):
        result = orch.run_triage(project)

    assert result["sessions_run"] == 1
    assert result["incomplete"] == 1
    assert result["success"] == 0
    assert result["failed"] == 0


def test_timeout_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("semgrep",)])

    import mcp.orchestrator as orch

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("subprocess.run", side_effect=TimeoutExpired(cmd="claude", timeout=300)),
    ):
        result = orch.run_triage(project)

    assert result["sessions_run"] == 1
    assert result["failed"] == 1
    assert result["success"] == 0
    assert result["incomplete"] == 0


def test_nonzero_exit_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("semgrep",)])

    import mcp.orchestrator as orch

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "some error"

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("subprocess.run", return_value=mock_result),
    ):
        result = orch.run_triage(project)

    assert result["sessions_run"] == 1
    assert result["failed"] == 1
    assert result["success"] == 0
    assert result["incomplete"] == 0


def test_missing_db_raises(tmp_path: Path) -> None:
    import mcp.orchestrator as orch

    with patch.object(orch, "_APP_ROOT", tmp_path):
        with pytest.raises(FileNotFoundError):
            orch.run_triage("nonexistent-project")


def test_standalone_import() -> None:
    import mcp.orchestrator  # noqa: F401

    assert callable(mcp.orchestrator.run_triage)
