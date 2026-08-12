"""Integration tests for triage batching across all tool types.

Exercises the production batching pipeline (combo discovery, fetch,
batch computation, persistence) with findings from every scanner
segment to catch silent skipping of unsupported or miskeyed segments.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.batching import compute_batches  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import (  # noqa: E402
    FindingRepository,
)
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import (  # noqa: E402
    TriageBatchRepository,
)
from tests.finding_helpers import normalize_test_findings  # noqa: E402

pytestmark = pytest.mark.integration


# -- Setup helpers --


def _make_repos(
    tmp_path: Path,
) -> tuple[
    ConnectionFactory,
    RunRepository,
    FindingRepository,
    TriageBatchRepository,
]:
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
    findings: list[dict[str, Any]],
    factory: ConnectionFactory,
) -> int:
    repo_ids: dict[str, int] = {}
    for f in findings:
        name = f.get("repo", "unknown")
        if name not in repo_ids:
            repo_ids[name] = _seed_repo(factory, name)
    findings = [{**f, "repo_id": repo_ids[f.get("repo", "unknown")]} for f in findings]
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))
    return run_id


def _batch_for(
    triage_repo: TriageBatchRepository,
    run_id: int,
    tool: str,
    repo: str,
    segment: str,
) -> list[list[dict[str, Any]]]:
    findings = triage_repo.fetch_active_findings_for_batching(
        run_id, tool, repo, segment
    )
    return compute_batches(findings)


# -- Finding builders --


def _make_sast_finding(
    tool: str = "semgrep",
    repo: str = "myrepo",
    file_path: str = "src/foo.py",
    rule_id: str = "r1",
    severity: str = "medium",
    risk_type: str = "injection",
    line_start: int = 10,
) -> dict[str, Any]:
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


def _make_web_finding(
    tool: str = "graphql-cop",
    repo: str = "myrepo",
    url: str = "http://example.com/graphql",
    severity: str = "medium",
    risk_type: str = "info_disclosure",
) -> dict[str, Any]:
    return {
        "tool": tool,
        "repo": repo,
        "segment": "web",
        "url": url,
        "severity": severity,
        "risk_type": risk_type,
    }


def _make_secrets_finding(
    tool: str = "gitleaks",
    repo: str = "myrepo",
    file_path: str = "config/.env",
    rule_id: str = "generic-api-key",
    severity: str = "high",
) -> dict[str, Any]:
    return {
        "tool": tool,
        "repo": repo,
        "segment": "secrets",
        "file_path": file_path,
        "rule_id": rule_id,
        "severity": severity,
    }


def _make_sca_finding(
    tool: str = "composer-audit",
    repo: str = "myrepo",
    package_name: str = "symfony/console",
    ecosystem: str = "Packagist",
    severity: str = "medium",
    vulnerability_id: str = "CVE-2024-1234",
) -> dict[str, Any]:
    return {
        "tool": tool,
        "repo": repo,
        "segment": "sca",
        "package_name": package_name,
        "ecosystem": ecosystem,
        "severity": severity,
        "vulnerability_id": vulnerability_id,
    }


class TestBatchingAllTools:
    """Pipeline tests: combo discovery -> fetch -> batch -> create."""

    def test_combo_discovery_all_segments(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        findings = [
            _make_sast_finding(repo="r1"),
            _make_web_finding(repo="r1"),
            _make_secrets_finding(repo="r1"),
            _make_sca_finding(repo="r1"),
        ]
        run_id = _seed_findings(run_repo, finding_repo, findings, factory)

        combos = triage_repo.get_active_finding_combos(run_id, frozenset())

        assert ("semgrep", "r1", "sast") in combos
        assert ("graphql-cop", "r1", "web") in combos
        assert ("gitleaks", "r1", "secrets") in combos
        assert ("composer-audit", "r1", "sca") in combos
        assert len(combos) == 4

    def test_sast_batches_produced(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        findings = [
            _make_sast_finding(file_path="src/a.py", line_start=1),
            _make_sast_finding(file_path="src/a.py", line_start=20),
            _make_sast_finding(file_path="src/b.py", line_start=5),
        ]
        run_id = _seed_findings(run_repo, finding_repo, findings, factory)

        batches = _batch_for(triage_repo, run_id, "semgrep", "myrepo", "sast")

        assert len(batches) >= 1
        all_ids = [f["id"] for b in batches for f in b]
        assert len(all_ids) == 3

    def test_web_batches_produced(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        findings = [
            _make_web_finding(
                url="http://example.com/login",
                risk_type="sqli",
            ),
            _make_web_finding(
                url="http://example.com/search",
                risk_type="xss",
            ),
        ]
        run_id = _seed_findings(run_repo, finding_repo, findings, factory)

        batches = _batch_for(triage_repo, run_id, "graphql-cop", "myrepo", "web")

        assert len(batches) >= 1
        all_ids = [f["id"] for b in batches for f in b]
        assert len(all_ids) == 2

    @pytest.mark.parametrize(
        ("tool", "segment", "builder"),
        [
            ("gitleaks", "secrets", _make_secrets_finding),
            ("composer-audit", "sca", _make_sca_finding),
        ],
        ids=["secrets", "sca"],
    )
    def test_excluded_segment_returns_empty(
        self,
        tmp_path: Path,
        tool: str,
        segment: str,
        builder: Any,
    ) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        findings = [builder(), builder(), builder()]
        run_id = _seed_findings(run_repo, finding_repo, findings, factory)

        fetched = triage_repo.fetch_active_findings_for_batching(
            run_id, tool, "myrepo", segment
        )
        batches = compute_batches(fetched)

        assert fetched == []
        assert batches == []

    def test_full_pipeline_creates_correct_batches(self, tmp_path: Path) -> None:
        factory, run_repo, finding_repo, triage_repo = _make_repos(tmp_path)
        findings = [
            _make_sast_finding(
                repo="r1",
                file_path="src/a.py",
                line_start=1,
            ),
            _make_sast_finding(
                repo="r1",
                file_path="src/a.py",
                line_start=20,
            ),
            _make_web_finding(
                tool="graphql-cop",
                repo="r1",
                url="http://example.com/graphql",
            ),
            _make_web_finding(
                tool="zap",
                repo="r1",
                url="http://example.com/login",
            ),
            _make_secrets_finding(repo="r1"),
            _make_sca_finding(repo="r1"),
        ]
        run_id = _seed_findings(run_repo, finding_repo, findings, factory)

        combos = triage_repo.get_active_finding_combos(run_id, frozenset())
        batch_counts: dict[str, int] = {}

        for tool, repo, segment in combos:
            fetched = triage_repo.fetch_active_findings_for_batching(
                run_id, tool, repo, segment
            )
            batches = compute_batches(fetched)
            created = triage_repo.create_batches(run_id, batches)
            batch_counts[f"{tool}/{segment}"] = len(created)

        assert batch_counts["semgrep/sast"] >= 1
        assert batch_counts["graphql-cop/web"] >= 1
        assert batch_counts["zap/web"] >= 1
        assert batch_counts["gitleaks/secrets"] == 0
        assert batch_counts["composer-audit/sca"] == 0

        with factory.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[0]
        expected = sum(batch_counts.values())
        assert total == expected
        assert total >= 3
