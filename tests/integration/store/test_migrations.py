"""Integration tests for the schema migration runner."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from infrastructure.store.migrations import (  # noqa: E402
    add_column_if_missing,
    run_pending,
)

pytestmark = pytest.mark.integration

_OLD_REPOSITORIES_DDL = """\
CREATE TABLE repositories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    ),
    deleted_at TEXT
)
"""

_EXPECTED_NEW_COLUMNS = {
    "path",
    "services_json",
    "xsstrike_crawl_level",
    "katana_headless",
    "katana_depth",
    "xsstrike_headers_json",
    "dalfox_headers_json",
    "katana_headers_json",
    "graphql_cop_headers_json",
    "auth_json",
    "url_seed_file",
}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row[0] is not None else 0


class TestMigrationRunnerOnFreshDB:
    """Fresh databases already have the correct schema via CREATE TABLE."""

    def test_sets_version_to_latest(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "fresh.db")
        factory.init_schema()
        with factory.connect() as conn:
            assert _current_version(conn) >= 1

    def test_all_repository_columns_present(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "fresh.db")
        factory.init_schema()
        with factory.connect() as conn:
            cols = _column_names(conn, "repositories")
        assert _EXPECTED_NEW_COLUMNS.issubset(cols)


class TestMigrationRunnerOnOldDB:
    """Old databases are missing columns that migrations must add."""

    def _make_old_db(self, db_path: Path) -> sqlite3.Connection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute(_OLD_REPOSITORIES_DDL)
        conn.commit()
        return conn

    def test_adds_missing_columns(self, tmp_path: Path) -> None:
        db_path = tmp_path / "old.db"
        old_conn = self._make_old_db(db_path)
        old_conn.close()

        factory = ConnectionFactory(db_path)
        factory.init_schema()

        with factory.connect() as conn:
            cols = _column_names(conn, "repositories")
        assert _EXPECTED_NEW_COLUMNS.issubset(cols)

    def test_sets_version(self, tmp_path: Path) -> None:
        db_path = tmp_path / "old.db"
        old_conn = self._make_old_db(db_path)
        old_conn.close()

        factory = ConnectionFactory(db_path)
        factory.init_schema()

        with factory.connect() as conn:
            assert _current_version(conn) == 3

    def test_preserves_existing_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "old.db"
        old_conn = self._make_old_db(db_path)
        old_conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            ("my-repo",),
        )
        old_conn.commit()
        old_conn.close()

        factory = ConnectionFactory(db_path)
        factory.init_schema()

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT name, services_json FROM repositories"
            ).fetchone()
        assert row[0] == "my-repo"
        services = json.loads(row[1])
        assert len(services) == 1
        assert services[0]["name"] == "default"


class TestMigrationIdempotency:
    def test_running_twice_is_safe(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "idem.db")
        factory.init_schema()
        factory.init_schema()

        with factory.connect() as conn:
            versions = conn.execute("SELECT version FROM schema_version").fetchall()
        assert len(versions) == 3
        assert versions[-1][0] == 3

    def test_skips_already_applied(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "skip.db")
        factory.init_schema()

        with factory.connect() as conn:
            first_count = _current_version(conn)

        with factory.connect() as conn:
            applied = run_pending(conn)

        assert applied == 0
        with factory.connect() as conn:
            assert _current_version(conn) == first_count


class TestAddColumnIfMissing:
    def test_adds_new_column(self, tmp_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_path / "helper.db"))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        assert add_column_if_missing(conn, "t", "foo", "TEXT")
        cols = _column_names(conn, "t")
        assert "foo" in cols
        conn.close()

    def test_skips_existing_column(self, tmp_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_path / "helper.db"))
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, foo TEXT)")
        assert not add_column_if_missing(conn, "t", "foo", "TEXT")
        conn.close()
