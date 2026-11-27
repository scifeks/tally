"""Tests that an unmigrated project database is refused with directions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory

pytestmark = pytest.mark.integration


class TestOldRunToolsGuard:
    def test_old_shape_run_tools_names_the_migration_script(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "findings.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE run_tools (id INTEGER PRIMARY KEY, repo TEXT)")
        conn.close()
        with pytest.raises(RuntimeError, match="scripts/migrate_tal_284.py"):
            ConnectionFactory(db_path).init_schema()
