"""Tests for TriageBatchRepository.create_batches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import TriageBatchRepository  # noqa: E402

pytestmark = pytest.mark.integration


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
    finding_repo.insert_findings(run_id, findings)
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
        _seed_findings(run_repo, finding_repo, findings, factory)
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
        _seed_findings(run_repo, finding_repo, findings, factory)
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
        _seed_findings(run_repo, finding_repo, findings, factory)
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
        _seed_findings(run_repo, finding_repo, findings, factory)
        run_id = run_repo.create_run({})
        count = repo.create_batches(run_id, "zap", "myrepo", "api")
        assert count >= 1
