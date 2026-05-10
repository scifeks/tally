"""Integration tests for FindingRepository.reset_tal_ids()."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository

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


def _upsert(
    repo: FindingRepository,
    run_repo: RunRepository,
    tool: str,
    extra: dict | None = None,
) -> int:
    run_id = run_repo.create_run({})
    row = {"tool": tool, "severity": "low", "profile": "default", **(extra or {})}
    repo.insert_findings(run_id, [row])
    with repo._factory.connect() as conn:
        fid = conn.execute(
            "SELECT id FROM findings WHERE tool=? ORDER BY id DESC LIMIT 1",
            (tool,),
        ).fetchone()["id"]
    return fid


class TestResetTalIds:
    def test_reset_tal_ids_nulls_all(
        self,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """After bulk_update_tal_ids sets IDs, reset_tal_ids NULLs every row."""
        id1 = _upsert(repo, run_repo, "semgrep", {"rule_id": "r1"})
        id2 = _upsert(repo, run_repo, "gitleaks", {"rule_id": "r2"})
        id3 = _upsert(repo, run_repo, "nmap", {"rule_id": "r3"})

        repo.bulk_update_tal_ids([("TAL-001", id1), ("TAL-002", id2), ("TAL-003", id3)])

        repo.reset_tal_ids()

        with repo._factory.connect() as conn:
            rows = conn.execute(
                "SELECT id, tal_id, tool, severity FROM findings ORDER BY id"
            ).fetchall()

        assert len(rows) == 3
        for row in rows:
            assert row["tal_id"] is None
        tools = {row["tool"] for row in rows}
        assert tools == {"semgrep", "gitleaks", "nmap"}
        severities = {row["severity"] for row in rows}
        assert severities == {3}

    def test_reset_tal_ids_on_empty_table_is_noop(
        self,
        repo: FindingRepository,
    ) -> None:
        """reset_tal_ids on an empty findings table raises no error."""
        repo.reset_tal_ids()
        with repo._factory.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 0
