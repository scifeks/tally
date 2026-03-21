"""Tests for RunRepository.add_run_tools."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


class TestAddRunTools:
    def test_inserts_row_per_tool(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = repo.create_run({})
        repo.add_run_tools(
            run_id,
            [
                {"tool": "gitleaks", "findings_count": 3},
                {"tool": "semgrep", "findings_count": 1},
            ],
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT tool FROM run_tools WHERE run_id = ?", (run_id,)
            ).fetchall()
        tools = [r["tool"] for r in rows]
        assert "gitleaks" in tools
        assert "semgrep" in tools
        assert len(tools) == 2

    def test_findings_count_stored(
        self, factory: ConnectionFactory, repo: RunRepository
    ) -> None:
        run_id = repo.create_run({})
        repo.add_run_tools(run_id, [{"tool": "nmap", "findings_count": 5}])
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT findings_count FROM run_tools WHERE run_id = ?", (run_id,)
            ).fetchone()
        assert row["findings_count"] == 5
