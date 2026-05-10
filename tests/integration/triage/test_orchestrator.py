"""Tests for triage orchestrator integration."""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.triage_agent import (  # noqa: E402
    PreparedTriageSession,
)
from application.triage.orchestrator import run_triage  # noqa: E402
from application.triage.runner import TriageRunner  # noqa: E402
from application.triage.verdict import (  # noqa: E402
    Verdict,
    VerdictParseError,
)
from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)

pytestmark = pytest.mark.integration

# Helpers


def _make_verdict(finding_id: int) -> Verdict:
    return Verdict(
        finding_id=finding_id,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="high",
        reasoning="test",
        remediation="fix",
        attack_vector="network",
        call_stack=[],
    )


class _StubAdapter:
    """Adapter stub returning canned Verdicts."""

    def __init__(
        self,
        *,
        side_effect: BaseException | None = None,
    ) -> None:
        self._side_effect = side_effect

    @contextmanager
    def prepare_session(self, *, project, run_id, app_root):
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(self, prompt, *, finding_id, timeout_seconds, cwd):
        if self._side_effect is not None:
            raise self._side_effect
        return _make_verdict(finding_id)


def _init_store(db_path: Path) -> None:
    factory = ConnectionFactory(db_path)
    factory.init_schema()


def _seed_scan_run(db_path: Path) -> None:
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
            "INSERT INTO findings (tool, triaged_at) VALUES (?, NULL)",
            (tool,),
        )
    conn.commit()
    conn.close()


def _make_db_active(
    db_path: Path,
    rows: list[tuple[str, str, str]],
) -> None:
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
            "INSERT INTO findings"
            " (tool, status, repo_id, segment, triaged_at)"
            " VALUES (?, 'active', ?, ?, NULL)",
            (tool, repo_ids[repo_name], segment),
        )
    conn.commit()
    conn.close()


# Fixtures


@pytest.fixture()
def project_db(tmp_path: Path):
    project = "test-project"
    db = tmp_path / "projects" / project / "sqlite" / "findings.db"

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "test-model",
                },
                "triage_inference": {"provider": "ollama"},
            }
        )
    )

    return project, tmp_path, db


def _make_tool_registry_mock(
    skip: bool = False, scan_segment: str = "sast"
) -> MagicMock:
    tool = MagicMock()
    tool.skip = skip
    tool.scan_segment = scan_segment
    reg = MagicMock()
    reg.get_tool.return_value = tool
    reg.get_all_tools.return_value = [tool]
    return reg


def _run_with_adapter(
    project: str,
    tmp_root: Path,
    adapter: _StubAdapter | None = None,
) -> dict:
    from infrastructure.store import make_store

    run_repo, finding_repo, triage_repo, audit_repo = make_store(str(tmp_root), project)
    with patch("application.triage.factory.TriageAgentFactory") as mock_factory:
        mock_factory.return_value.create.return_value = adapter or _StubAdapter()
        return run_triage(
            project,
            _make_tool_registry_mock(),
            app_root=tmp_root,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
        )


# Tests


def test_all_skip_tools(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db(db, [("nmap",), ("tree-sitter",)])

    result = _run_with_adapter(project, tmp_root)

    assert result["sessions_run"] == 0
    assert result["success"] == 0
    assert result["failed"] == 0
    assert result["incomplete"] == 0


def test_success_outcome(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    result = _run_with_adapter(project, tmp_root)

    assert result["sessions_run"] == 1
    assert result["success"] == 1
    assert result["failed"] == 0
    assert result["incomplete"] == 0


def test_failed_outcome_on_parse_error(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    adapter = _StubAdapter(side_effect=VerdictParseError("bad json"))
    result = _run_with_adapter(project, tmp_root, adapter)

    assert result["sessions_run"] == 1
    assert result["failed"] == 1
    assert result["success"] == 0
    assert result["incomplete"] == 0


def test_failed_outcome_on_exception(project_db) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    adapter = _StubAdapter(side_effect=RuntimeError("agent crashed"))
    result = _run_with_adapter(project, tmp_root, adapter)

    assert result["sessions_run"] == 1
    assert result["failed"] == 1
    assert result["success"] == 0
    assert result["incomplete"] == 0


def test_missing_db_raises(tmp_path: Path) -> None:
    mock = MagicMock()
    with pytest.raises(FileNotFoundError):
        run_triage(
            "nonexistent-project",
            _make_tool_registry_mock(),
            app_root=tmp_path,
            run_repo=mock,
            finding_repo=mock,
            triage_repo=mock,
            audit_repo=mock,
            repo_paths={},
        )


def test_standalone_import() -> None:
    import application.triage.orchestrator  # noqa: F401

    assert callable(application.triage.orchestrator.run_triage)


# Batching phase tests


def test_stale_batches_for_current_run_are_reset(
    project_db,
) -> None:
    from infrastructure.store import make_store

    project, tmp_root, db = project_db
    _make_db(db, [])

    run_repo, _, _, _ = make_store(tmp_root, project)
    factory = ConnectionFactory(db)
    run_id = run_repo.create_run({})

    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data,"
            " status, run_attempts)"
            " VALUES (?, '[]', '[]', 'in_progress', 0)",
            (run_id,),
        )

    with patch(
        "infrastructure.store.repositories.runs.RunRepository.create_run",
        return_value=run_id,
    ):
        _run_with_adapter(project, tmp_root)

    with factory.connect() as conn:
        row = conn.execute(
            "SELECT status FROM triage_batches WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    assert row is not None
    assert row["status"] != "in_progress"


def test_stale_batches_other_run_not_touched(
    project_db,
) -> None:
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
                " (run_id, finding_ids, batch_data,"
                " status, run_attempts)"
                " VALUES (?, '[]', '[]', 'in_progress', 0)",
                (rid,),
            )

    with patch(
        "infrastructure.store.repositories.runs.RunRepository.latest_run_id",
        return_value=run_id_a,
    ):
        _run_with_adapter(project, tmp_root)

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT run_id, status FROM triage_batches ORDER BY run_id"
        ).fetchall()

    status_by_run = {r["run_id"]: r["status"] for r in rows}
    assert status_by_run[run_id_a] != "in_progress"
    assert status_by_run[run_id_b] == "in_progress"


def test_create_triage_batches_called_per_combo(
    project_db,
) -> None:
    project, tmp_root, db = project_db
    _make_db_active(
        db,
        [
            ("semgrep", "repo1", "sast"),
            ("semgrep", "repo1", "sast"),
            ("zap", "repo1", "api"),
        ],
    )

    from infrastructure.store import make_store

    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_root, project)
    with (
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository"
            ".fetch_active_findings_for_batching",
            return_value=[],
        ) as mock_fetch,
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository.create_batches",
            return_value=1,
        ),
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository.reset_stale_batches",
            return_value=0,
        ),
        patch("application.triage.factory.TriageAgentFactory") as mock_factory,
    ):
        mock_factory.return_value.create.return_value = _StubAdapter()
        run_triage(
            project,
            _make_tool_registry_mock(),
            app_root=tmp_root,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
        )

    assert mock_fetch.call_count == 2
    calls = {(c.args[0], c.args[1], c.args[2]) for c in mock_fetch.call_args_list}
    assert ("semgrep", "repo1", "sast") in calls
    assert ("zap", "repo1", "api") in calls


def test_batching_error_aborts_before_session_prep(
    project_db,
) -> None:
    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    from infrastructure.store import make_store

    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_root, project)
    with (
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository"
            ".fetch_active_findings_for_batching",
            side_effect=RuntimeError("db locked"),
        ),
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository.reset_stale_batches",
            return_value=0,
        ),
        patch.object(TriageRunner, "_prepare_session") as mock_prepare,
        patch("application.triage.factory.TriageAgentFactory") as mock_factory,
    ):
        mock_factory.return_value.create.return_value = _StubAdapter()
        with pytest.raises(RuntimeError, match="Batching failed"):
            run_triage(
                project,
                _make_tool_registry_mock(),
                app_root=tmp_root,
                run_repo=run_repo,
                finding_repo=finding_repo,
                triage_repo=triage_repo,
                audit_repo=audit_repo,
                repo_paths={},
            )

    mock_prepare.assert_not_called()


def test_batch_count_reported(project_db, capsys) -> None:
    from infrastructure.store import make_store

    project, tmp_root, db = project_db
    _make_db_active(db, [("semgrep", "repo1", "sast")])

    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_root, project)
    with (
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository"
            ".fetch_active_findings_for_batching",
            return_value=[],
        ),
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository.create_batches",
            return_value=3,
        ),
        patch(
            "infrastructure.store.repositories.triage"
            ".TriageBatchRepository.reset_stale_batches",
            return_value=0,
        ),
        patch("application.triage.factory.TriageAgentFactory") as mock_factory,
    ):
        mock_factory.return_value.create.return_value = _StubAdapter()
        run_triage(
            project,
            _make_tool_registry_mock(),
            app_root=tmp_root,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
        )

    out = capsys.readouterr().out
    assert "3" in out
    assert "semgrep" in out
