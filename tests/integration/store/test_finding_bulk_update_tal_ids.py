"""Integration tests for FindingRepository.bulk_update_tal_ids()."""

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
    repo.upsert_findings(run_id, [row])
    with repo._factory.connect() as conn:
        fid = conn.execute(
            "SELECT id FROM findings WHERE tool=? ORDER BY id DESC LIMIT 1",
            (tool,),
        ).fetchone()["id"]
    return fid


class TestBulkUpdateTalIds:
    def test_bulk_update_tal_ids_assigns_correctly(
        self,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """TAL-IDs are written to the correct rows; unassigned rows stay NULL."""
        id1 = _upsert(repo, run_repo, "semgrep", {"rule_id": "r1"})
        id2 = _upsert(repo, run_repo, "gitleaks", {"rule_id": "r2"})
        id3 = _upsert(repo, run_repo, "nmap", {"rule_id": "r3"})

        repo.bulk_update_tal_ids([("TAL-001", id1), ("TAL-003", id3)])

        with repo._factory.connect() as conn:
            row1 = conn.execute(
                "SELECT tal_id FROM findings WHERE id = ?", (id1,)
            ).fetchone()
            row2 = conn.execute(
                "SELECT tal_id FROM findings WHERE id = ?", (id2,)
            ).fetchone()
            row3 = conn.execute(
                "SELECT tal_id FROM findings WHERE id = ?", (id3,)
            ).fetchone()

        assert row1["tal_id"] == "TAL-001"
        assert row2["tal_id"] is None
        assert row3["tal_id"] == "TAL-003"

    def test_bulk_update_tal_ids_empty_list_is_noop(
        self,
        repo: FindingRepository,
    ) -> None:
        """Passing an empty list raises no error and leaves the table unchanged."""
        repo.bulk_update_tal_ids([])
        with repo._factory.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 0

    def test_bulk_update_tal_ids_overwrites_existing(
        self,
        repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """A second call to bulk_update_tal_ids overwrites the previous TAL-ID."""
        id1 = _upsert(repo, run_repo, "semgrep", {"rule_id": "r1"})

        repo.bulk_update_tal_ids([("TAL-001", id1)])
        repo.bulk_update_tal_ids([("TAL-999", id1)])

        with repo._factory.connect() as conn:
            row = conn.execute(
                "SELECT tal_id FROM findings WHERE id = ?", (id1,)
            ).fetchone()

        assert row["tal_id"] == "TAL-999"
