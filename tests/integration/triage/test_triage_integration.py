"""Integration tests for the triage pipeline (no agent invocation).

These tests exercise the full pipeline end-to-end against real
repositories, real batch creation, real claiming, and real finding
updates, with the triage backend port replaced by a stub that returns
canned Verdict objects.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.triage_agent import (  # noqa: E402
    PreparedTriageSession,
)
from application.triage.runner import (  # noqa: E402
    TriageResult,
    TriageRunner,
)
from application.triage.verdict import Verdict  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from infrastructure.store.repositories.findings import (  # noqa: E402
    FindingRepository,
)
from infrastructure.store.repositories.runs import (  # noqa: E402
    RunRepository,
)
from tests.finding_helpers import normalize_test_findings  # noqa: E402

pytestmark = pytest.mark.integration

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "repo": "testrepo",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "potential",
    "file_path": "src/app.py",
    "rule_id": "python.sqli",
    "description": "SQL injection",
}


def _make_verdict(finding_id: int) -> Verdict:
    return Verdict(
        finding_id=finding_id,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="high",
        reasoning="test reasoning",
        remediation="fix it",
        attack_vector="network",
        call_stack=[],
    )


class _StubTriageBackend:
    """Returns a canned Verdict for each finding."""

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        return _make_verdict(finding_id)


def _seed_repo(factory: ConnectionFactory, name: str = "testrepo") -> int:
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, path) VALUES (?, ?)",
            (name, "/tmp/fakerepo"),
        )
        return cur.lastrowid  # type: ignore[return-value]


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    n: int = 1,
    overrides: dict | None = None,
    factory: ConnectionFactory | None = None,
) -> int:
    repo_id: int | None = _seed_repo(factory) if factory is not None else None
    run_id = run_repo.create_run({})
    batch = [
        {
            **_BASE_FINDING,
            "file_path": f"src/file{i}.py",
            **({"repo_id": repo_id} if repo_id is not None else {}),
            **(overrides or {}),
        }
        for i in range(n)
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(batch))
    return run_id


def _all_finding_ids(factory: ConnectionFactory) -> list[int]:
    with factory.connect() as conn:
        rows = conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
    return [r["id"] for r in rows]


def _make_mock_semgrep() -> MagicMock:
    t = MagicMock()
    t.name = "semgrep"
    t.skip = False
    t.scan_segment = "sast"
    return t


def _make_runner_real(
    tmp_path: Path,
    project: str = "testproject",
    *,
    triage_backend: _StubTriageBackend | None = None,
    cancel_token=None,
) -> tuple[
    TriageRunner,
    ConnectionFactory,
    RunRepository,
    FindingRepository,
]:
    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_path, project)
    factory = ConnectionFactory(
        tmp_path / "projects" / project / "sqlite" / "findings.db"
    )

    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        None,
        tmp_path,
        tool_registry=MagicMock(),
        triage_backend=triage_backend or _StubTriageBackend(),
        cancel_token=cancel_token,
        session_timeout_seconds=300,
        finding_repo=finding_repo,
        repo_paths={"testrepo": Path("/tmp/fakerepo")},
        triaged_by="claudecode",
    )
    return runner, factory, run_repo, finding_repo


def _mock_reg(runner: TriageRunner) -> MagicMock:
    return runner._tool_registry  # type: ignore[return-value]


# Group 2: End-to-end pipeline with real store


def test_pipeline_batch_creates_pending_batches(
    tmp_path: Path,
) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.batch()

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM triage_batches WHERE status = 'pending'"
        ).fetchall()
    assert len(rows) >= 1


def test_pipeline_finding_marked_enriched(
    tmp_path: Path,
) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run()

    fid = _all_finding_ids(factory)[0]
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT enriched, triaged_at, triaged_by FROM findings WHERE id = ?",
            (fid,),
        ).fetchone()
    assert row["enriched"] == 1
    assert row["triaged_at"] is not None
    assert row["triaged_by"] == "claudecode"


def test_pipeline_result_counts_match(
    tmp_path: Path,
) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        result = runner.run()

    assert isinstance(result, TriageResult)
    assert result.sessions_run == 1
    assert result.success == 1


# Group 3: Multi-batch regression


def test_all_batches_processed_no_stuck_in_progress(
    tmp_path: Path,
) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        normalize_test_findings(
            [
                {
                    **_BASE_FINDING,
                    "file_path": "src/alpha.py",
                    "repo_id": repo_id,
                },
                {
                    **_BASE_FINDING,
                    "file_path": "src/beta.py",
                    "rule_id": "python.xss",
                    "repo_id": repo_id,
                },
            ]
        ),
    )

    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run()

    with factory.connect() as conn:
        stuck = conn.execute(
            "SELECT * FROM triage_batches WHERE status IN ('pending', 'in_progress')"
        ).fetchall()
    assert len(stuck) == 0


def test_both_findings_enriched(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        normalize_test_findings(
            [
                {
                    **_BASE_FINDING,
                    "file_path": "src/a.py",
                    "repo_id": repo_id,
                },
                {
                    **_BASE_FINDING,
                    "file_path": "src/b.py",
                    "rule_id": "python.xss",
                    "repo_id": repo_id,
                },
            ]
        ),
    )

    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run()

    with factory.connect() as conn:
        rows = conn.execute("SELECT enriched, triaged_by FROM findings").fetchall()
    assert all(r["enriched"] == 1 for r in rows)
    assert all(r["triaged_by"] == "claudecode" for r in rows)
