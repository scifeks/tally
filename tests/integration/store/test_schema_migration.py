"""Integration tests for the new findings table columns."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402

pytestmark = pytest.mark.integration


def _column_names(factory: ConnectionFactory) -> set[str]:
    with factory.connect() as conn:
        rows = conn.execute("PRAGMA table_info(findings)").fetchall()
    return {row["name"] for row in rows}


def _insert_and_read(factory: ConnectionFactory) -> dict[str, object]:
    """Insert a minimal row and return the new columns' values."""
    from infrastructure.store.repositories.runs import RunRepository

    run_repo = RunRepository(factory)
    run_id = run_repo.create_run({})

    with factory.connect() as conn:
        conn.execute(
            "INSERT INTO findings (fingerprint, run_id, tool, severity) "
            "VALUES ('fp-migration-test', ?, 'test', 'low')",
            (run_id,),
        )
        row = conn.execute(
            "SELECT should_report, business_impact, tal_id "
            "FROM findings WHERE fingerprint = 'fp-migration-test'"
        ).fetchone()
    return dict(row)


class TestSchemaNewColumns:
    def test_all_three_columns_present(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        cols = _column_names(factory)
        assert "should_report" in cols
        assert "business_impact" in cols
        assert "tal_id" in cols

    def test_should_report_default_is_0(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        defaults = _insert_and_read(factory)
        assert defaults["should_report"] == 0

    def test_business_impact_default_is_null(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        defaults = _insert_and_read(factory)
        assert defaults["business_impact"] is None

    def test_tal_id_default_is_null(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        defaults = _insert_and_read(factory)
        assert defaults["tal_id"] is None


class TestForeignKeyEnforcement:
    def test_foreign_key_enforcement_is_on(self, tmp_path: Path) -> None:
        """PRAGMA foreign_keys is ON after connect()."""
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        with factory.connect() as conn:
            result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_foreign_key_violation_raises(self, tmp_path: Path) -> None:
        """A declared FK constraint is enforced when foreign_keys=ON."""
        import sqlite3

        factory = ConnectionFactory(tmp_path / "test_fk.db")
        with factory.connect() as conn:
            conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            conn.execute(
                "CREATE TABLE child "
                "(id INTEGER PRIMARY KEY, "
                "parent_id INTEGER REFERENCES parent(id))"
            )
        with pytest.raises(sqlite3.IntegrityError):
            with factory.connect() as conn:
                conn.execute("INSERT INTO child (parent_id) VALUES (99999)")
