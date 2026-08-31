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
