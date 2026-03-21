"""Tests for FindingRepository.get_finding."""

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


class TestGetFinding:
    def test_returns_dict(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(run_repo, repo, [{"tool": "nmap", "severity": "low"}])
        with repo._factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]
        result = repo.get_finding(fid)
        assert isinstance(result, dict)
        assert result["tool"] == "nmap"

    def test_returns_none_for_missing(self, repo: FindingRepository) -> None:
        assert repo.get_finding(999_999) is None
