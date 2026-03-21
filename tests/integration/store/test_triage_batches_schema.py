"""Integration tests for triage_batches table schema."""

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


def _make_store(
    tmp_path: Path,
) -> tuple[ConnectionFactory, RunRepository, FindingRepository]:
    factory = ConnectionFactory(
        tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    )
    factory.init_schema()
    return factory, RunRepository(factory), FindingRepository(factory)


class TestTriageBatchesSchema:
    def test_table_exists(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        with factory.connect() as conn:
            sql = (
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND name='triage_batches'"
            )
            row = conn.execute(sql).fetchone()
        assert row is not None

    def test_all_columns_exist(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        with factory.connect() as conn:
            rows = conn.execute("PRAGMA table_info(triage_batches)").fetchall()
        col_names = {r[1] for r in rows}
        expected = {
            "id",
            "run_id",
            "finding_ids",
            "batch_data",
            "status",
            "run_attempts",
            "created_at",
            "started_at",
            "completed_at",
        }
        assert expected == col_names

    def _insert_minimal(self, factory: ConnectionFactory) -> int:
        with factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO triage_batches (finding_ids, batch_data) VALUES (?, ?)",
                ("[1,2]", "[]"),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def test_status_defaults_to_pending(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT status FROM triage_batches WHERE id=?", (row_id,)
            ).fetchone()
        assert row[0] == "pending"

    def test_run_attempts_defaults_to_zero(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT run_attempts FROM triage_batches WHERE id=?", (row_id,)
            ).fetchone()
        assert row[0] == 0

    def test_created_at_auto_populated(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT created_at FROM triage_batches WHERE id=?", (row_id,)
            ).fetchone()
        assert row[0] is not None

    def test_started_at_and_completed_at_nullable(self, tmp_path: Path) -> None:
        factory, _, _ = _make_store(tmp_path)
        row_id = self._insert_minimal(factory)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT started_at, completed_at FROM triage_batches WHERE id=?",
                (row_id,),
            ).fetchone()
        assert row[0] is None
        assert row[1] is None
