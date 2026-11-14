"""Integration test for the finding_history source CHECK migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory

pytestmark = pytest.mark.integration


class TestFindingHistorySourceConstraint:
    def test_mcp_triage_source_accepted(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        factory = ConnectionFactory(db)
        factory.init_schema()
        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO findings (id, tool, severity)"
                " VALUES (1, 'semgrep', 'high')"
            )
            conn.execute(
                "INSERT INTO finding_history"
                " (finding_id, timestamp, before_values,"
                "  after_values, source)"
                " VALUES (1, '2026-01-01', '{}', '{}', 'mcp_triage')"
            )
            row = conn.execute(
                "SELECT source FROM finding_history WHERE finding_id = 1"
            ).fetchone()
            assert row[0] == "mcp_triage"

    def test_cli_source_accepted(self, tmp_path: Path) -> None:
        db = tmp_path / "test.db"
        factory = ConnectionFactory(db)
        factory.init_schema()
        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO findings (id, tool, severity)"
                " VALUES (1, 'semgrep', 'high')"
            )
            conn.execute(
                "INSERT INTO finding_history"
                " (finding_id, timestamp, before_values,"
                "  after_values, source)"
                " VALUES (1, '2026-01-01', '{}', '{}', 'cli')"
            )
            row = conn.execute(
                "SELECT source FROM finding_history WHERE finding_id = 1"
            ).fetchone()
            assert row[0] == "cli"

    def test_cli_migration_preserves_existing_rows(self, tmp_path: Path) -> None:
        """Verify m0008 adds 'cli' without losing existing history."""

        db = tmp_path / "test.db"
        factory = ConnectionFactory(db)
        factory.init_schema()
        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO findings (id, tool, severity)"
                " VALUES (1, 'semgrep', 'high')"
            )
            conn.execute(
                "INSERT INTO finding_history"
                " (finding_id, timestamp, before_values,"
                "  after_values, source)"
                " VALUES (1, '2026-01-01', '{}', '{}', 'web_ui')"
            )
            count_before = conn.execute(
                "SELECT COUNT(*) FROM finding_history"
            ).fetchone()[0]
            assert count_before == 1

        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO finding_history"
                " (finding_id, timestamp, before_values,"
                "  after_values, source)"
                " VALUES (1, '2026-01-02', '{}', '{}', 'cli')"
            )
            rows = conn.execute(
                "SELECT source FROM finding_history ORDER BY timestamp"
            ).fetchall()
            assert [r[0] for r in rows] == ["web_ui", "cli"]

    def test_invalid_source_rejected(self, tmp_path: Path) -> None:
        import sqlite3

        db = tmp_path / "test.db"
        factory = ConnectionFactory(db)
        factory.init_schema()
        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO findings (id, tool, severity)"
                " VALUES (1, 'semgrep', 'high')"
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO finding_history"
                    " (finding_id, timestamp, before_values,"
                    "  after_values, source)"
                    " VALUES (1, '2026-01-01', '{}', '{}',"
                    "  'bogus')"
                )
