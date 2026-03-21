# Disambiguation: this file contains TestFindingTypeJsonEach extracted from
# test_finding_repository.py. It differs from test_finding_type_json_each.py in
# test method names and fixture setup (uses repo/run_repo fixtures rather than
# _make_store helper with inline run creation).

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

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    findings: list[dict],
) -> int:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, findings)
    return run_id


class TestFindingTypeJsonEach:
    def test_exact_match_secret_does_not_return_vulnerability(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {
                    "tool": "gitleaks",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_number": 1,
                    "finding_type": "secret",
                },
                {
                    "tool": "semgrep",
                    "rule_id": "r2",
                    "file_path": "b.py",
                    "line_start": 1,
                    "finding_type": "vulnerability",
                },
            ],
        )
        results = repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert all(r["metadata"]["finding_type"] == ["secret"] for r in results)
        assert not any(r["metadata"].get("tool") == "semgrep" for r in results)

    def test_exact_match_multi_value(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {"tool": "gitleaks", "rule_id": "r1", "finding_type": "secret"},
                {"tool": "semgrep", "rule_id": "r2", "finding_type": "vulnerability"},
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                },
            ],
        )
        results = repo.search(
            {
                "conditions": [("finding_type", "=", ["secret", "vulnerability"])],
                "page": 1,
                "page_size": 200,
            }
        )
        tools = {r["metadata"]["tool"] for r in results}
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert "nmap" not in tools

    def test_partial_match_vuln(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {"tool": "semgrep", "rule_id": "r2", "finding_type": "vulnerability"},
                {"tool": "gitleaks", "rule_id": "r1", "finding_type": "secret"},
            ],
        )
        results = repo.search(
            {
                "conditions": [("finding_type", "~=", ["vuln"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert len(results) >= 1
        assert all(r["metadata"]["tool"] == "semgrep" for r in results)

    def test_exact_match_empty_result(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [
                {
                    "tool": "nmap",
                    "ip_address": "1.2.3.4",
                    "finding_type": "informational",
                }
            ],
        )
        results = repo.search(
            {
                "conditions": [("finding_type", "=", ["secret"])],
                "page": 1,
                "page_size": 200,
            }
        )
        assert results == []
