"""Tests for TriageBatchRepository."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.store.connection import ConnectionFactory  # noqa: E402
from core.store.repositories.findings import FindingRepository  # noqa: E402
from core.store.repositories.runs import RunRepository  # noqa: E402
from core.store.repositories.triage import TriageBatchRepository  # noqa: E402


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> TriageBatchRepository:
    return TriageBatchRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


def _seed_findings(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
) -> int:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, findings)
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
        "segment": "api",
        "url": url,
        "severity": severity,
        "risk_type": risk_type,
    }


def _seed_batch(
    factory: ConnectionFactory,
    run_repo: RunRepository,
    status: str = "pending",
    attempts: int = 0,
) -> int:
    run_id = run_repo.create_run({})
    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO triage_batches"
            " (run_id, finding_ids, batch_data, status, run_attempts)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                run_id,
                json.dumps([1, 2]),
                json.dumps([{"id": 1}, {"id": 2}]),
                status,
                attempts,
            ),
        )
    return run_id


# ---------------------------------------------------------------------------
# create_batches
# ---------------------------------------------------------------------------


class TestCreateBatches:
    def test_writes_correct_batch_count(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=1),
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=2),
            _make_sast_finding(file_path="src/b.py", risk_type="xss", line_start=1),
            _make_sast_finding(file_path="src/b.py", risk_type="xss", line_start=2),
        ]
        _seed_findings(run_repo, finding_repo, findings)
        run_id = run_repo.create_run({})
        count = repo.create_batches(run_id, "semgrep", "myrepo", "sast")
        assert count == 2
        with factory.connect() as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[
                0
            ]
        assert row_count == 2

    def test_batch_row_fields(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli"),
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=20),
        ]
        _seed_findings(run_repo, finding_repo, findings)
        run_id = run_repo.create_run({})
        repo.create_batches(run_id, "semgrep", "myrepo", "sast")
        with factory.connect() as conn:
            row = dict(conn.execute("SELECT * FROM triage_batches LIMIT 1").fetchone())
        assert row["run_id"] == run_id
        assert row["status"] == "pending"
        assert row["run_attempts"] == 0

    def test_finding_ids_match_batch_data(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        findings = [
            _make_sast_finding(file_path="src/a.py", risk_type="sqli", line_start=i)
            for i in range(1, 4)
        ]
        _seed_findings(run_repo, finding_repo, findings)
        run_id = run_repo.create_run({})
        repo.create_batches(run_id, "semgrep", "myrepo", "sast")
        with factory.connect() as conn:
            row = dict(conn.execute("SELECT * FROM triage_batches LIMIT 1").fetchone())
        finding_ids = json.loads(row["finding_ids"])
        batch_data = json.loads(row["batch_data"])
        assert finding_ids == [f["id"] for f in batch_data]

    def test_empty_findings_writes_nothing(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = run_repo.create_run({})
        count = repo.create_batches(run_id, "semgrep", "myrepo", "sast")
        assert count == 0
        with factory.connect() as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[
                0
            ]
        assert row_count == 0

    def test_api_segment_uses_url_query(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        findings = [
            _make_api_finding(url="http://example.com/api/login", risk_type="xss"),
            _make_api_finding(url="http://example.com/api/search", risk_type="sqli"),
        ]
        _seed_findings(run_repo, finding_repo, findings)
        run_id = run_repo.create_run({})
        count = repo.create_batches(run_id, "zap", "myrepo", "api")
        assert count >= 1


# ---------------------------------------------------------------------------
# claim_batch / complete_batch
# ---------------------------------------------------------------------------


class TestClaimAndComplete:
    def test_claim_sets_in_progress_increments_attempts(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        result = repo.claim_batch(run_id)
        assert result is not None
        assert result["status"] == "in_progress"
        assert result["run_attempts"] == 1
        assert result["started_at"] is not None

    def test_two_concurrent_claims_no_duplication(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        results: list[dict | None] = [None, None]

        def _claim(idx: int) -> None:
            results[idx] = repo.claim_batch(run_id)

        t1 = threading.Thread(target=_claim, args=(0,))
        t2 = threading.Thread(target=_claim, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1

    def test_no_pending_batches_returns_none(
        self, repo: TriageBatchRepository, run_repo: RunRepository
    ) -> None:
        run_id = run_repo.create_run({})
        assert repo.claim_batch(run_id) is None

    def test_exhausted_attempts_never_claimed(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="pending", attempts=3)
        assert repo.claim_batch(run_id) is None

    def test_complete_success(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch["id"], "success")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status, completed_at FROM triage_batches WHERE id = ?",
                (batch["id"],),
            ).fetchone()
        assert row["status"] == "success"
        assert row["completed_at"] is not None

    def test_complete_failed(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo)
        batch = repo.claim_batch(run_id)
        assert batch is not None
        repo.complete_batch(batch["id"], "failed")
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE id = ?", (batch["id"],)
            ).fetchone()
        assert row["status"] == "failed"

    def test_claim_scoped_to_correct_run_id(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_a = run_repo.create_run({})
        run_b = _seed_batch(factory, run_repo)
        assert repo.claim_batch(run_a) is None
        result_b = repo.claim_batch(run_b)
        assert result_b is not None
        assert result_b["run_id"] == run_b


# ---------------------------------------------------------------------------
# reset_stale_batches
# ---------------------------------------------------------------------------


class TestResetStaleBatches:
    def test_resets_in_progress_to_pending(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_id = _seed_batch(factory, run_repo, status="in_progress")
        count = repo.reset_stale_batches(run_id)
        assert count == 1
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE run_id = ?", (run_id,)
            ).fetchone()
        assert row["status"] == "pending"

    def test_does_not_touch_other_run(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
    ) -> None:
        run_a = _seed_batch(factory, run_repo, status="in_progress")
        run_b = _seed_batch(factory, run_repo, status="in_progress")
        repo.reset_stale_batches(run_a)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE run_id = ?", (run_b,)
            ).fetchone()
        assert row["status"] == "in_progress"


# ---------------------------------------------------------------------------
# get_active_finding_combos
# ---------------------------------------------------------------------------


class TestGetActiveFindings:
    def test_returns_distinct_combos(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        findings = [
            _make_sast_finding(tool="semgrep", repo="r1"),
            _make_sast_finding(tool="semgrep", repo="r1"),  # duplicate
            _make_api_finding(tool="zap", repo="r1"),
        ]
        _seed_findings(run_repo, finding_repo, findings)
        combos = repo.get_active_finding_combos(frozenset())
        assert ("semgrep", "r1", "sast") in combos
        assert ("zap", "r1", "api") in combos
        assert len([c for c in combos if c == ("semgrep", "r1", "sast")]) == 1

    def test_excludes_skip_tools(
        self,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        _seed_findings(run_repo, finding_repo, [_make_sast_finding(tool="nmap")])
        combos = repo.get_active_finding_combos(frozenset({"nmap"}))
        assert not any(c[0] == "nmap" for c in combos)
