"""Tests for TriageBatchRepository.get_active_finding_combos."""

from __future__ import annotations

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
from tests.finding_helpers import normalize_test_findings  # noqa: E402

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
        run_id = _seed_findings(run_repo, finding_repo, findings, factory)
        combos = repo.get_active_finding_combos(run_id, frozenset())
        assert ("semgrep", "r1", "sast") in combos
        assert ("zap", "r1", "web") in combos
        assert len([c for c in combos if c == ("semgrep", "r1", "sast")]) == 1

    def test_excludes_skip_tools(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        run_id = _seed_findings(
            run_repo, finding_repo, [_make_sast_finding(tool="nmap")], factory
        )
        combos = repo.get_active_finding_combos(run_id, frozenset({"nmap"}))
        assert not any(c[0] == "nmap" for c in combos)

    def test_scopes_to_run_id(
        self,
        factory: ConnectionFactory,
        repo: TriageBatchRepository,
        run_repo: RunRepository,
        finding_repo: FindingRepository,
    ) -> None:
        run1 = _seed_findings(
            run_repo,
            finding_repo,
            [_make_sast_finding(tool="semgrep", repo="r1")],
            factory,
        )
        run2 = _seed_findings(
            run_repo,
            finding_repo,
            [_make_api_finding(tool="zap", repo="r1")],
            factory,
        )
        combos1 = repo.get_active_finding_combos(run1, frozenset())
        combos2 = repo.get_active_finding_combos(run2, frozenset())
        assert ("semgrep", "r1", "sast") in combos1
        assert ("zap", "r1", "web") not in combos1
        assert ("zap", "r1", "web") in combos2
        assert ("semgrep", "r1", "sast") not in combos2
