"""Integration tests for SQLite store meta list fields."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from infrastructure.store import make_store
from infrastructure.store.connection import ConnectionFactory
from tests.finding_helpers import normalize_test_findings

pytestmark = pytest.mark.integration

_PROJECT_NAME = "test-proj"


class _TestStore:
    """Thin wrapper that exposes a SQLiteStore-compatible surface for tests."""

    def __init__(
        self, factory: ConnectionFactory, run_repo: object, finding_repo: object
    ) -> None:
        self._factory = factory
        self._run_repo = run_repo
        self._finding_repo = finding_repo
        self._db_path = factory.db_path

    def create_run(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._run_repo.create_run(*args, **kwargs)  # type: ignore[attr-defined]

    def insert_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.insert_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def search(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.search(*args, **kwargs)  # type: ignore[attr-defined]

    def get_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.get_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def delete_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.delete_findings(*args, **kwargs)  # type: ignore[attr-defined]

    def get_tool_meta_keys(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.get_tool_meta_keys(*args, **kwargs)  # type: ignore[attr-defined]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        self._factory.init_schema()


def _make_store(tmp_path: Path) -> _TestStore:
    run_repo, finding_repo, _, _ = make_store(tmp_path, _PROJECT_NAME)
    factory = ConnectionFactory(
        tmp_path / "projects" / _PROJECT_NAME / "sqlite" / "findings.db"
    )
    return _TestStore(factory, run_repo, finding_repo)


class TestMetaListFields:
    def test_comma_list_stored_as_json_array(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            normalize_test_findings(
                [
                    {
                        "tool": "semgrep",
                        "rule_id": "r1",
                        "file_path": "a.py",
                        "line_start": 1,
                        # Comma-joined string as stored by ChromaDB ingestor
                        "technology": "python, flask",
                        "references": "https://cwe.mitre.org, https://owasp.org",
                    }
                ]
            ),
        )
        conn = store._connect()
        row = conn.execute("SELECT meta FROM findings").fetchone()
        meta = json.loads(row[0])
        assert isinstance(meta["technology"], list)
        assert "python" in meta["technology"]
        assert isinstance(meta["references"], list)
        assert len(meta["references"]) == 2
