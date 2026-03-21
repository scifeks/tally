"""Tests for FindingRepository.get_tool_meta_keys."""

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


class TestGetToolMetaKeys:
    def test_returns_zero_count_for_unknown_tool(self, repo: FindingRepository) -> None:
        count, keys = repo.get_tool_meta_keys("nonexistent")
        assert count == 0
        assert keys == set()

    def test_returns_meta_keys(
        self, repo: FindingRepository, run_repo: RunRepository
    ) -> None:
        _seed(
            run_repo,
            repo,
            [{"tool": "semgrep", "risk_type": "sqli", "file_path": "a.py"}],
        )
        count, keys = repo.get_tool_meta_keys("semgrep")
        assert count == 1
        assert "risk_type" in keys
