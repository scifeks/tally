"""Integration tests for saved-scans + arg-profiles schema additions."""

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


def _factory(tmp_path: Path) -> ConnectionFactory:
    factory = ConnectionFactory(
        tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    )
    factory.init_schema()
    return factory


def _columns(factory: ConnectionFactory, table: str) -> dict[str, sqlite3.Row]:
    with factory.connect() as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"]: r for r in rows}


class TestSavedScansSchema:
    _NEW_TABLES = (
        "tool_arg_profiles",
        "tool_overrides",
        "saved_scans",
        "saved_scan_repos",
        "saved_scan_tools",
        "saved_scan_arg_profiles",
    )

    def test_all_new_tables_created(self, tmp_path: Path) -> None:
        factory = _factory(tmp_path)
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type='table' AND name IN (?, ?, ?, ?, ?, ?)",
                self._NEW_TABLES,
            ).fetchall()
        assert {r[0] for r in rows} == set(self._NEW_TABLES)

    def test_tool_arg_profiles_columns(self, tmp_path: Path) -> None:
        cols = _columns(_factory(tmp_path), "tool_arg_profiles")
        assert set(cols) == {
            "id",
            "tool_name",
            "name",
            "args",
            "created_at",
            "updated_at",
        }

    def test_tool_overrides_args_mode_default_and_check(self, tmp_path: Path) -> None:
        factory = _factory(tmp_path)
        cols = _columns(factory, "tool_overrides")
        assert "args_mode" in cols

        with factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO tool_overrides (tool_name, type, location, path)"
                " VALUES (?, ?, ?, ?)",
                ("semgrep", "repo", "local", "/usr/bin/semgrep"),
            )
            inserted_id = cur.lastrowid
            row = conn.execute(
                "SELECT args_mode FROM tool_overrides WHERE id=?", (inserted_id,)
            ).fetchone()
            assert row["args_mode"] == "stock"

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO tool_overrides"
                    " (tool_name, args_mode, type, location, path)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("gitleaks", "bogus", "repo", "local", "/usr/bin/gitleaks"),
                )

    def test_saved_scans_skip_enrichment_default(self, tmp_path: Path) -> None:
        factory = _factory(tmp_path)
        cols = _columns(factory, "saved_scans")
        assert set(cols) == {
            "id",
            "name",
            "skip_enrichment",
            "created_at",
            "updated_at",
        }

        with factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO saved_scans (name) VALUES (?)", ("nightly",)
            )
            row = conn.execute(
                "SELECT skip_enrichment FROM saved_scans WHERE id=?",
                (cur.lastrowid,),
            ).fetchone()
            assert row["skip_enrichment"] == 0

    def test_saved_scan_tools_redesigned_shape(self, tmp_path: Path) -> None:
        cols = _columns(_factory(tmp_path), "saved_scan_tools")
        assert set(cols) == {"saved_scan_id", "tool_name"}

    def test_saved_scan_arg_profiles_restrict_blocks_profile_delete(
        self, tmp_path: Path
    ) -> None:
        factory = _factory(tmp_path)
        cols = _columns(factory, "saved_scan_arg_profiles")
        assert set(cols) == {"saved_scan_id", "arg_profile_id"}

        with factory.connect() as conn:
            profile_cur = conn.execute(
                "INSERT INTO tool_arg_profiles (tool_name, name) VALUES (?, ?)",
                ("gitleaks", "verbose"),
            )
            profile_id = profile_cur.lastrowid
            scan_cur = conn.execute(
                "INSERT INTO saved_scans (name) VALUES (?)", ("weekly",)
            )
            scan_id = scan_cur.lastrowid
            conn.execute(
                "INSERT INTO saved_scan_arg_profiles"
                " (saved_scan_id, arg_profile_id) VALUES (?, ?)",
                (scan_id, profile_id),
            )

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM tool_arg_profiles WHERE id=?", (profile_id,))

    def test_scan_runs_saved_scan_id_set_null_on_delete(self, tmp_path: Path) -> None:
        factory = _factory(tmp_path)
        cols = _columns(factory, "scan_runs")
        assert "saved_scan_id" in cols
        # FK column is nullable.
        assert cols["saved_scan_id"]["notnull"] == 0

        with factory.connect() as conn:
            scan_cur = conn.execute(
                "INSERT INTO saved_scans (name) VALUES (?)", ("monthly",)
            )
            scan_id = scan_cur.lastrowid
            run_cur = conn.execute(
                "INSERT INTO scan_runs (project_id, saved_scan_id) VALUES (?, ?)",
                (1, scan_id),
            )
            run_id = run_cur.lastrowid
            conn.execute("DELETE FROM saved_scans WHERE id=?", (scan_id,))
            row = conn.execute(
                "SELECT saved_scan_id FROM scan_runs WHERE id=?", (run_id,)
            ).fetchone()
            assert row["saved_scan_id"] is None

    def test_run_tools_arg_profile_snapshot_nullable(self, tmp_path: Path) -> None:
        factory = _factory(tmp_path)
        cols = _columns(factory, "run_tools")
        assert "arg_profile_snapshot" in cols
        assert cols["arg_profile_snapshot"]["notnull"] == 0

        with factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO run_tools (run_id, tool) VALUES (?, ?)",
                (1, "gitleaks"),
            )
            row = conn.execute(
                "SELECT arg_profile_snapshot FROM run_tools WHERE id=?",
                (cur.lastrowid,),
            ).fetchone()
            assert row["arg_profile_snapshot"] is None
