"""Integration tests for TriageBatchRepository.create_batches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.batching import (  # noqa: E402
    batch_size_for_segment,
    compute_batches,
)
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import TriageBatchRepository  # noqa: E402
from tests.finding_helpers import normalize_test_findings  # noqa: E402


def _batch_for(
    triage_repo: TriageBatchRepository, run_id: int, tool: str, repo: str, segment: str
) -> list[list[dict]]:
    """Replicate the runner's read-then-compute step for the writer tests."""
    findings = triage_repo.fetch_active_findings_for_batching(
        run_id, tool, repo, segment
    )
    return compute_batches(
        findings,
        max_findings_per_batch=batch_size_for_segment(segment),
    )


pytestmark = pytest.mark.integration


def _make_repos(
    tmp_path: Path,
) -> tuple[ConnectionFactory, RunRepository, FindingRepository, TriageBatchRepository]:
    factory = ConnectionFactory(
        tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    )
    factory.init_schema()
    return (
        factory,
        RunRepository(factory),
        FindingRepository(factory),
        TriageBatchRepository(factory),
    )


def _seed_repo(factory: ConnectionFactory, name: str) -> int:
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            (name,),
        )
        return cur.lastrowid  # type: ignore[return-value]


def _seed_findings(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
    factory: ConnectionFactory | None = None,
) -> int:
    if factory is not None:
        repo_ids: dict[str, int] = {}
        for f in findings:
            name = f.get("repo", "unknown")
            if name not in repo_ids:
                repo_ids[name] = _seed_repo(factory, name)
        findings = [
            {**f, "repo_id": repo_ids[f.get("repo", "unknown")]} for f in findings
        ]
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))
    return run_id


def _make_sast_finding(
    tool: str = "semgrep",
    repo: str = "myrepo",
    file_path: str = "src/foo.py",
    rule_id: str = "r1",
    severity: str = "medium",
    risk_type: str = "injection",
    line_start: int = 10,
) -> dict:
    return {
        "tool": tool,
        "repo": repo,
        "segment": "sast",
        "file_path": file_path,
        "rule_id": rule_id,
        "severity": severity,
        "risk_type": risk_type,
        "line_start": line_start,
    }


def _make_api_finding(
    tool: str = "zap",
    repo: str = "myrepo",
    url: str = "http://example.com/api/v1",
    severity: str = "medium",
    risk_type: str = "xss",
) -> dict:
    return {
        "tool": tool,
        "repo": repo,
        "segment": "web",
        "url": url,
        "severity": severity,
        "risk_type": risk_type,
    }


class TestCreateTriageBatches:
    def test_writes_correct_batch_count(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=1),
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=2),
            _make_sast_finding(file_path="src/b.py", risk_type="xss", line_start=1),
            _make_sast_finding(file_path="src/b.py", risk_type="xss", line_start=2),
        ]
        seed_run_id = _seed_findings(run_repo, finding_repo, findings, factory)
        created = triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        assert len(created) == 2
        with factory.connect() as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[
                0
            ]
        assert row_count == 2

    def test_batch_row_fields(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli"),
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=20),
        ]
        seed_run_id = _seed_findings(run_repo, finding_repo, findings, factory)
        triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        with factory.connect() as conn:
            row = dict(conn.execute("SELECT * FROM triage_batches LIMIT 1").fetchone())
        assert row["run_id"] == run_id
        assert row["status"] == "pending"
        assert row["run_attempts"] == 0

    def test_finding_ids_match_batch_data(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=i)
            for i in range(1, 4)
        ]
        seed_run_id = _seed_findings(run_repo, finding_repo, findings, factory)
        triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        with factory.connect() as conn:
            row = dict(conn.execute("SELECT * FROM triage_batches LIMIT 1").fetchone())
        finding_ids = json.loads(row["finding_ids"])
        batch_data = json.loads(row["batch_data"])
        assert finding_ids == [f["id"] for f in batch_data]

    def test_started_at_completed_at_null(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        seed_run_id = _seed_findings(
            run_repo, finding_repo, [_make_sast_finding()], factory
        )
        triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        with factory.connect() as conn:
            row = dict(conn.execute("SELECT * FROM triage_batches LIMIT 1").fetchone())
        assert row["started_at"] is None
        assert row["completed_at"] is None

    def test_not_idempotent(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=1),
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=2),
        ]
        seed_run_id = _seed_findings(run_repo, finding_repo, findings, factory)
        triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        with factory.connect() as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[
                0
            ]
        assert row_count == 2

    def test_empty_findings_writes_nothing(self, tmp_path: Path) -> None:
        factory, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        seed_run_id = run_repo.create_run({})
        created = triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "semgrep", "myrepo", "sast")
        )
        assert len(created) == 0
        with factory.connect() as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[
                0
            ]
        assert row_count == 0

    def test_web_segment_batched_size_one(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        findings = [
            _make_api_finding(url="http://example.com/api/login", risk_type="xss"),
            _make_api_finding(url="http://example.com/api/search", risk_type="sqli"),
        ]
        seed_run_id = _seed_findings(run_repo, finding_repo, findings, factory)
        created = triage_repo.create_batches(
            run_id, _batch_for(triage_repo, seed_run_id, "zap", "myrepo", "web")
        )
        assert len(created) == 2
        assert all(count == 1 for _, count in created)


class TestListForRunCancelledSemantics:
    """Pin the two-mode contract of list_for_run.

    The default (``include_cancelled=False``) is only for the resume
    path, which treats canceled rows as stale prior-attempt relics.
    Every display-time surface (SSE snapshot, detail endpoint) must
    pass ``include_cancelled=True`` to render the true state.
    """

    def test_default_excludes_cancelled_rows(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        triage_repo.create_batches(
            run_id,
            [
                [{"id": 1, "tool": "semgrep", "segment": "sast"}],
                [{"id": 2, "tool": "semgrep", "segment": "sast"}],
                [{"id": 3, "tool": "semgrep", "segment": "sast"}],
            ],
        )
        triage_repo.complete_batch(1, "completed")
        triage_repo.cancel_remaining(run_id)

        rows = triage_repo.list_for_run(run_id)
        assert [r.status for r in rows] == ["completed"]

    def test_include_cancelled_returns_all_rows(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        triage_repo.create_batches(
            run_id,
            [
                [{"id": 1, "tool": "semgrep", "segment": "sast"}],
                [{"id": 2, "tool": "semgrep", "segment": "sast"}],
                [{"id": 3, "tool": "semgrep", "segment": "sast"}],
            ],
        )
        triage_repo.complete_batch(1, "completed")
        triage_repo.cancel_remaining(run_id)

        rows = triage_repo.list_for_run(run_id, include_cancelled=True)
        assert sorted(r.status for r in rows) == [
            "cancelled",
            "cancelled",
            "completed",
        ]


class TestListForRunAfterBatchIdFilter:
    """Pin the after_batch_id filter contract for display-time reads."""

    def test_after_batch_id_hides_earlier_rows(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        created = triage_repo.create_batches(
            run_id,
            [
                [{"id": 1, "tool": "semgrep", "segment": "sast"}],
                [{"id": 2, "tool": "semgrep", "segment": "sast"}],
                [{"id": 3, "tool": "semgrep", "segment": "sast"}],
            ],
        )
        first_batch_id = created[0][0]
        rows = triage_repo.list_for_run(
            run_id,
            include_cancelled=True,
            after_batch_id=first_batch_id,
        )
        assert [r.id for r in rows] == [first_batch_id + 1, first_batch_id + 2]

    def test_after_batch_id_none_returns_all(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        triage_repo.create_batches(
            run_id,
            [
                [{"id": 1, "tool": "semgrep", "segment": "sast"}],
                [{"id": 2, "tool": "semgrep", "segment": "sast"}],
            ],
        )
        assert len(triage_repo.list_for_run(run_id, after_batch_id=None)) == 2


class TestSummarizeForRunAfterBatchIdFilter:
    def test_summary_counts_only_batches_after_boundary(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        created = triage_repo.create_batches(
            run_id,
            [
                [{"id": 1, "tool": "semgrep", "segment": "sast"}],
                [{"id": 2, "tool": "semgrep", "segment": "sast"}],
                [{"id": 3, "tool": "semgrep", "segment": "sast"}],
            ],
        )
        boundary = created[0][0]
        triage_repo.complete_batch(created[1][0], "completed")
        summary = triage_repo.summarize_for_run(run_id, after_batch_id=boundary)
        assert summary is not None
        assert summary.total_batches == 2
        assert summary.processed_findings == 1


class TestMaxBatchIdForRun:
    def test_returns_none_when_no_batches(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        assert triage_repo.max_batch_id_for_run(run_id) is None

    def test_returns_max_id(self, tmp_path: Path) -> None:
        _, run_repo, _, triage_repo = _make_repos(tmp_path)
        run_id = run_repo.create_run({})
        created = triage_repo.create_batches(
            run_id,
            [
                [{"id": 1, "tool": "semgrep", "segment": "sast"}],
                [{"id": 2, "tool": "semgrep", "segment": "sast"}],
            ],
        )
        assert triage_repo.max_batch_id_for_run(run_id) == created[-1][0]
