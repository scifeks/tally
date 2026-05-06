"""Tests for mcp.orchestrator."""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

import application.triage.runner as triage_mod  # noqa: E402
from application.triage.orchestrator import run_triage  # noqa: E402
from application.triage.runner import TriageRunner  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402

pytestmark = pytest.mark.integration

# Helpers


def _init_store(db_path: Path) -> None:
    """Initialise the real schema via ConnectionFactory (no schema drift)."""
    factory = ConnectionFactory(db_path)
    factory.init_schema()


def _seed_scan_run(db_path: Path) -> None:
    """Insert a minimal scan_runs row so triage has something to operate on.

    Phase 6: triage runs against the latest scan_run; the runner raises
    NoScanRunError if no scan_runs exist. These integration tests don't
    care which scan_run id is used; they just need the lookup to
    return something non-None.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO scan_runs (args) VALUES ('{}')")
    conn.commit()
    conn.close()


def _make_db(db_path: Path, rows: list[tuple[str]]) -> None:
    _init_store(db_path)
    _seed_scan_run(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
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
    """Seed active findings with (tool, repo_name, segment) tuples."""

    _init_store(db_path)
    _seed_scan_run(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    repo_ids: dict[str, int] = {}
    for tool, repo_name, segment in rows:
        if repo_name not in repo_ids:
            cur = conn.execute(
                "INSERT INTO repositories (name) VALUES (?)",
                (repo_name,),
            )
            repo_ids[repo_name] = cur.lastrowid  # type: ignore[assignment]
        conn.execute(
            "INSERT INTO findings (tool, status, repo_id, segment, triaged_at)"
            " VALUES (?, 'active', ?, ?, NULL)",
            (tool, repo_ids[repo_name], segment),
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


# Fixtures


@pytest.fixture()
def project_db(tmp_path: Path):
    """Create a minimal project DB and patch _APP_ROOT."""
    project = "test-project"
    db = tmp_path / "projects" / project / "sqlite" / "findings.db"
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()
    return project, tmp_path, db


# Helpers


def _make_tool_registry_mock(
    skip: bool = False, scan_segment: str = "sast"
) -> MagicMock:
    """Return a tool_registry MagicMock whose get_tool() returns a runnable tool."""
    tool = MagicMock()
    tool.skip = skip
    tool.scan_segment = scan_segment
    reg = MagicMock()
    reg.get_tool.return_value = tool
    reg.get_all_tools.return_value = [tool]
    return reg


def _run_with_root(project: str, tmp_root: Path) -> dict:
    """Invoke run_triage with _APP_ROOT patched."""
    with patch.object(triage_mod, "_APP_ROOT", tmp_root):
        return run_triage(project, _make_tool_registry_mock())


# Tests


def test_all_skip_tools(project_db, caplog) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("nmap",), ("tree-sitter",)])

    result = _run_with_root(project, tmp_root)

    assert result["sessions_run"] == 0
    assert result["success"] == 0
    assert result["failed"] == 0
    assert result["incomplete"] == 0


def test_mcp_json_written(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])  # non-skip → session runs

    import json

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
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch("subprocess.run", side_effect=fake_run),
    ):
        run_triage(project, _make_tool_registry_mock())

    assert captured.get("exists") is True
    assert project in str(captured.get("data", {}))


def test_success_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

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
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch("subprocess.run", side_effect=fake_run),
    ):
        result = run_triage(project, _make_tool_registry_mock())

    assert result["sessions_run"] == 1
    assert result["success"] == 1
    assert result["failed"] == 0
    assert result["incomplete"] == 0


def test_incomplete_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch("subprocess.run", return_value=mock_result),
    ):
        result = run_triage(project, _make_tool_registry_mock())

    assert result["sessions_run"] == 1
    assert result["incomplete"] == 1
    assert result["success"] == 0
    assert result["failed"] == 0


def test_timeout_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch("subprocess.run", side_effect=TimeoutExpired(cmd="claude", timeout=300)),
    ):
        result = run_triage(project, _make_tool_registry_mock())

    assert result["sessions_run"] == 1
    assert result["failed"] == 1
    assert result["success"] == 0
    assert result["incomplete"] == 0


def test_nonzero_exit_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "some error"

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch("subprocess.run", return_value=mock_result),
    ):
        result = run_triage(project, _make_tool_registry_mock())

    assert result["sessions_run"] == 1
    assert result["failed"] == 1
    assert result["success"] == 0
    assert result["incomplete"] == 0


def test_missing_db_raises(tmp_path: Path) -> None:
    with patch.object(triage_mod, "_APP_ROOT", tmp_path):
        with pytest.raises(FileNotFoundError):
            run_triage("nonexistent-project", _make_tool_registry_mock())


def test_standalone_import() -> None:
    import application.triage.orchestrator  # noqa: F401

    assert callable(application.triage.orchestrator.run_triage)


# Batching phase tests


def test_stale_batches_for_current_run_are_reset(project_db) -> None:
    """in_progress batches for the current run_id are reset and then processed."""
    from infrastructure.store import make_store

    project, tmp_root, db = project_db
    _make_db(db, [])

    run_repo, _, _, _ = make_store(tmp_root, project)
    factory = ConnectionFactory(db)
    run_id = run_repo.create_run({})

    # Insert a stale in_progress batch for this run
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts)"
            " VALUES (?, '[]', '[]', 'in_progress', 0)",
            (run_id,),
        )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch(
            "infrastructure.store.repositories.runs.RunRepository.create_run",
            return_value=run_id,
        ),
        patch("subprocess.run", return_value=mock_result),
    ):
        run_triage(project, _make_tool_registry_mock())

    with factory.connect() as conn:
        row = conn.execute(
            "SELECT status FROM triage_batches WHERE run_id = ?", (run_id,)
        ).fetchone()
    assert row is not None
    assert row["status"] != "in_progress"


def test_stale_batches_other_run_not_touched(project_db) -> None:
    """in_progress batches from a different run_id are not reset."""
    from infrastructure.store import make_store

    project, tmp_root, db = project_db
    _make_db(db, [])

    run_repo, _, _, _ = make_store(tmp_root, project)
    factory = ConnectionFactory(db)
    run_id_a = run_repo.create_run({})
    run_id_b = run_repo.create_run({})

    for rid in (run_id_a, run_id_b):
        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO triage_batches"
                " (run_id, finding_ids, batch_data, status, run_attempts)"
                " VALUES (?, '[]', '[]', 'in_progress', 0)",
                (rid,),
            )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch(
            "infrastructure.store.repositories.runs.RunRepository.latest_run_id",
            return_value=run_id_a,
        ),
        patch("subprocess.run", return_value=mock_result),
    ):
        run_triage(project, _make_tool_registry_mock())

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT run_id, status FROM triage_batches ORDER BY run_id"
        ).fetchall()

    status_by_run = {r["run_id"]: r["status"] for r in rows}
    assert status_by_run[run_id_a] != "in_progress"
    assert status_by_run[run_id_b] == "in_progress"


def test_create_triage_batches_called_per_combo(project_db) -> None:
    """create_triage_batches is called once per distinct tool/repo/segment combo."""
    project, tmp_root, db = project_db
    _make_db_active(
        db,
        [
            ("semgrep", "repo1", "sast"),
            ("semgrep", "repo1", "sast"),  # duplicate; same combo
            ("zap", "repo1", "api"),
        ],
    )

    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stderr = ""

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.fetch_active_findings_for_batching",
            return_value=[],
        ) as mock_fetch,
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.create_batches",
            return_value=1,
        ),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.reset_stale_batches",
            return_value=0,
        ),
        patch("subprocess.run", return_value=mock_run),
    ):
        run_triage(project, _make_tool_registry_mock())

    assert mock_fetch.call_count == 2
    calls = {(c.args[0], c.args[1], c.args[2]) for c in mock_fetch.call_args_list}
    assert ("semgrep", "repo1", "sast") in calls
    assert ("zap", "repo1", "api") in calls


def test_batching_error_aborts_before_mcp_json(project_db) -> None:
    """Batching failures abort before session prep."""
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.fetch_active_findings_for_batching",
            side_effect=RuntimeError("db locked"),
        ),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.reset_stale_batches",
            return_value=0,
        ),
        patch.object(TriageRunner, "_prepare_session") as mock_prepare,
    ):
        with pytest.raises(RuntimeError, match="Batching failed"):
            run_triage(project, _make_tool_registry_mock())

    mock_prepare.assert_not_called()


def test_batch_count_reported(project_db, capsys) -> None:
    """Batch count and combo identifier appear in stdout."""
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stderr = ""

    with (
        patch.object(triage_mod, "_APP_ROOT", tmp_root),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.fetch_active_findings_for_batching",
            return_value=[],
        ),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.create_batches",
            return_value=3,
        ),
        patch(
            "infrastructure.store.repositories.triage.TriageBatchRepository.reset_stale_batches",
            return_value=0,
        ),
        patch("subprocess.run", return_value=mock_run),
    ):
        run_triage(project, _make_tool_registry_mock())

    out = capsys.readouterr().out
    assert "3" in out
    assert "semgrep" in out
