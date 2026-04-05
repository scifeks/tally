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
    finding_repo.insert_findings(run_id, findings)
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


class TestGetByIds:
    def test_get_by_ids_empty_list_returns_empty(self, repo: FindingRepository) -> None:
        """get_by_ids([]) returns [] with no error."""
        result = repo.get_by_ids([])
        assert result == []

    def test_get_by_ids_missing_ids_silently_omitted(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        """get_by_ids with non-existent IDs silently omits them."""
        _seed(
            run_repo,
            repo,
            [
                {"tool": "nmap", "severity": "low"},
                {"tool": "semgrep", "severity": "high"},
            ],
        )
        with repo._factory.connect() as conn:
            rows = conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
        id1 = rows[0]["id"]
        id2 = rows[1]["id"]

        result = repo.get_by_ids([id1, 99999, id2])
        assert len(result) == 2
        returned_ids = {r["id"] for r in result}
        assert id1 in returned_ids
        assert id2 in returned_ids
        assert 99999 not in returned_ids

    def test_get_by_ids_returns_correct_tool(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        """Returned dicts contain expected tool values."""
        _seed(run_repo, repo, [{"tool": "gitleaks", "severity": "high"}])
        with repo._factory.connect() as conn:
            fid = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()["id"]
        result = repo.get_by_ids([fid])
        assert len(result) == 1
        assert result[0]["tool"] == "gitleaks"
        assert result[0]["id"] == fid
