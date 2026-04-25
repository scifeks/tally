"""Integration tests for the runs -> scan_runs rename and run_tools extension.

Phase 5.1 renamed the legacy ``runs`` table to ``scan_runs`` and added
nine columns to ``run_tools``. The migration must:

- create ``scan_runs`` on a fresh DB with all new columns
- on a legacy DB (where only ``runs`` exists), copy id/args/created_at
  rows preserving primary keys and drop ``runs``
- be idempotent: running ``init_schema`` twice on either flavour is a
  no-op for already-migrated tables
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402

pytestmark = pytest.mark.integration


def _table_exists(factory: ConnectionFactory, name: str) -> bool:
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    return row is not None


def _column_names(factory: ConnectionFactory, table: str) -> set[str]:
    with factory.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _create_legacy_runs(db_path: Path) -> None:
    """Build a database that looks like Phase 4 (only ``runs`` exists)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE runs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " args TEXT,"
            " created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO runs (id, args, created_at) VALUES (?, ?, ?)",
            (1, '{"tool": "gitleaks"}', "2026-04-24T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO runs (id, args, created_at) VALUES (?, ?, ?)",
            (2, '{"tool": "semgrep"}', "2026-04-24T00:01:00+00:00"),
        )
        conn.execute(
            "CREATE TABLE run_tools ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " run_id INTEGER, tool TEXT,"
            " findings_count INTEGER DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO run_tools (run_id, tool, findings_count)"
            " VALUES (1, 'gitleaks', 3)"
        )
        conn.commit()
    finally:
        conn.close()


class TestFreshDatabase:
    def test_scan_runs_table_created(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "fresh.db")
        factory.init_schema()
        assert _table_exists(factory, "scan_runs")
        assert not _table_exists(factory, "runs")

    def test_scan_runs_has_phase_5_columns(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "fresh.db")
        factory.init_schema()
        cols = _column_names(factory, "scan_runs")
        for required in (
            "id",
            "project_id",
            "args",
            "created_at",
            "status",
            "started_at",
            "finished_at",
            "repo_ids",
            "tool_ids",
            "domains",
            "skip_enrichment",
            "findings_count",
        ):
            assert required in cols, f"missing column {required!r}"

    def test_run_tools_has_phase_5_columns(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "fresh.db")
        factory.init_schema()
        cols = _column_names(factory, "run_tools")
        for required in (
            "repo",
            "domain",
            "status",
            "started_at",
            "finished_at",
            "exit_code",
            "skip_reason",
            "enriched_count",
            "total_to_enrich",
        ):
            assert required in cols, f"missing column {required!r}"


class TestLegacyMigration:
    def test_rows_copied_preserving_id(self, tmp_path: Path) -> None:
        db_path = tmp_path / "legacy.db"
        _create_legacy_runs(db_path)

        factory = ConnectionFactory(db_path)
        factory.init_schema()

        assert not _table_exists(factory, "runs")
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT id, args, created_at FROM scan_runs ORDER BY id"
            ).fetchall()
        assert [(r["id"], r["args"]) for r in rows] == [
            (1, '{"tool": "gitleaks"}'),
            (2, '{"tool": "semgrep"}'),
        ]

    def test_run_tools_columns_added_idempotently(self, tmp_path: Path) -> None:
        db_path = tmp_path / "legacy.db"
        _create_legacy_runs(db_path)

        factory = ConnectionFactory(db_path)
        factory.init_schema()

        cols = _column_names(factory, "run_tools")
        assert {"repo", "domain", "status", "exit_code"}.issubset(cols)

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT tool, findings_count, repo, status"
                " FROM run_tools WHERE run_id = 1"
            ).fetchone()
        assert row["tool"] == "gitleaks"
        assert row["findings_count"] == 3
        assert row["repo"] is None
        assert row["status"] is None


class TestIdempotency:
    def test_migration_is_idempotent_on_fresh_db(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "fresh.db")
        factory.init_schema()
        factory.init_schema()  # second run must not raise
        assert _table_exists(factory, "scan_runs")
        assert not _table_exists(factory, "runs")

    def test_migration_is_idempotent_on_migrated_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "legacy.db"
        _create_legacy_runs(db_path)
        factory = ConnectionFactory(db_path)
        factory.init_schema()
        factory.init_schema()  # already-migrated, must not duplicate
        with factory.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        assert count == 2
