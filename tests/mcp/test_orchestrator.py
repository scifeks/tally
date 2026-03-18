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

from tally_mcp.orchestrator import run_triage  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE,
    tool TEXT,
    severity TEXT,
    status TEXT,
    segment TEXT,
    repo TEXT,
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


def _make_db_active(
    db_path: Path,
    rows: list[tuple[str, str, str]],
) -> None:
    """Seed active findings with (tool, repo, segment) tuples."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    for tool, repo, segment in rows:
        conn.execute(
            "INSERT INTO findings (tool, status, repo, segment, triaged_at)"
            " VALUES (?, 'active', ?, ?, NULL)",
            (tool, repo, segment),
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

    import tally_mcp.orchestrator as orch

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

    import tally_mcp.orchestrator as orch

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

    import tally_mcp.orchestrator as orch

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

    import tally_mcp.orchestrator as orch

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

    import tally_mcp.orchestrator as orch

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

    import tally_mcp.orchestrator as orch

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
    import tally_mcp.orchestrator as orch

    with patch.object(orch, "_APP_ROOT", tmp_path):
        with pytest.raises(FileNotFoundError):
            orch.run_triage("nonexistent-project")


def test_standalone_import() -> None:
    import tally_mcp.orchestrator  # noqa: F401

    assert callable(tally_mcp.orchestrator.run_triage)


# ---------------------------------------------------------------------------
# Batching phase tests
# ---------------------------------------------------------------------------


def test_stale_batches_for_current_run_are_reset(project_db) -> None:
    """in_progress batches for the current run_id are reset to pending."""
    from core.store.sqlite_store import SQLiteStore

    project, tmp_root, db = project_db
    _make_db(db, [])

    store = SQLiteStore(tmp_root, project)
    run_id = store.create_run({})

    # Insert a stale in_progress batch for this run
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts)"
            " VALUES (?, '[]', '[]', 'in_progress', 0)",
            (run_id,),
        )

    import tally_mcp.orchestrator as orch

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("core.store.sqlite_store.SQLiteStore.create_run", return_value=run_id),
    ):
        orch.run_triage(project)

    with store._connect() as conn:
        row = conn.execute(
            "SELECT status FROM triage_batches WHERE run_id = ?", (run_id,)
        ).fetchone()
    assert row is not None
    assert row["status"] == "pending"


def test_stale_batches_other_run_not_touched(project_db) -> None:
    """in_progress batches from a different run_id are not reset."""
    from core.store.sqlite_store import SQLiteStore

    project, tmp_root, db = project_db
    _make_db(db, [])

    store = SQLiteStore(tmp_root, project)
    run_id_a = store.create_run({})
    run_id_b = store.create_run({})

    for rid in (run_id_a, run_id_b):
        with store._connect() as conn:
            conn.execute(
                "INSERT INTO triage_batches"
                " (run_id, finding_ids, batch_data, status, run_attempts)"
                " VALUES (?, '[]', '[]', 'in_progress', 0)",
                (rid,),
            )

    import tally_mcp.orchestrator as orch

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch("core.store.sqlite_store.SQLiteStore.create_run", return_value=run_id_a),
    ):
        orch.run_triage(project)

    with store._connect() as conn:
        rows = conn.execute(
            "SELECT run_id, status FROM triage_batches ORDER BY run_id"
        ).fetchall()

    status_by_run = {r["run_id"]: r["status"] for r in rows}
    assert status_by_run[run_id_a] == "pending"
    assert status_by_run[run_id_b] == "in_progress"


def test_create_triage_batches_called_per_combo(project_db) -> None:
    """create_triage_batches is called once per distinct tool/repo/segment combo."""
    project, tmp_root, db = project_db
    _make_db_active(
        db,
        [
            ("semgrep", "repo1", "sast"),
            ("semgrep", "repo1", "sast"),  # duplicate — same combo
            ("zap", "repo1", "api"),
        ],
    )

    import tally_mcp.orchestrator as orch

    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stderr = ""

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch(
            "core.store.sqlite_store.SQLiteStore.create_triage_batches",
            return_value=1,
        ) as mock_create,
        patch("core.store.sqlite_store.SQLiteStore.create_run", return_value=1),
        patch(
            "core.store.sqlite_store.SQLiteStore.reset_stale_triage_batches",
            return_value=0,
        ),
        patch("subprocess.run", return_value=mock_run),
    ):
        orch.run_triage(project)

    assert mock_create.call_count == 2
    calls = {(c.args[1], c.args[2], c.args[3]) for c in mock_create.call_args_list}
    assert ("semgrep", "repo1", "sast") in calls
    assert ("zap", "repo1", "api") in calls


def test_batching_error_aborts_before_mcp_json(project_db) -> None:
    """A batching error raises RuntimeError and _write_mcp_json is not called."""
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    import tally_mcp.orchestrator as orch

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch(
            "core.store.sqlite_store.SQLiteStore.create_triage_batches",
            side_effect=RuntimeError("db locked"),
        ),
        patch("core.store.sqlite_store.SQLiteStore.create_run", return_value=1),
        patch(
            "core.store.sqlite_store.SQLiteStore.reset_stale_triage_batches",
            return_value=0,
        ),
        patch.object(orch, "_write_mcp_json") as mock_write,
    ):
        with pytest.raises(RuntimeError, match="Batching failed"):
            orch.run_triage(project)

    mock_write.assert_not_called()


def test_batch_count_reported(project_db, capsys) -> None:
    """Batch count and combo identifier appear in stdout."""
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    import tally_mcp.orchestrator as orch

    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stderr = ""

    with (
        patch.object(orch, "_APP_ROOT", tmp_root),
        patch(
            "core.store.sqlite_store.SQLiteStore.create_triage_batches",
            return_value=3,
        ),
        patch("core.store.sqlite_store.SQLiteStore.create_run", return_value=1),
        patch(
            "core.store.sqlite_store.SQLiteStore.reset_stale_triage_batches",
            return_value=0,
        ),
        patch("subprocess.run", return_value=mock_run),
    ):
        orch.run_triage(project)

    out = capsys.readouterr().out
    assert "3" in out
    assert "semgrep" in out
