"""Integration tests for SQLite store D2 OSV aliases list round-trip."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.store import make_store
from infrastructure.store.connection import ConnectionFactory

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


class TestD2OsvSearch:
    _OSV_FINDING = {
        "tool": "osv-scanner",
        "domain": "sca",
        "finding_type": "dependency",
        "severity": "high",
        "package_name": "lodash",
        "vulnerability_id": "GHSA-abc",
        "ecosystem": "npm",
        "aliases": "CVE-2021-1234, CVE-2021-5678",
        "lockfile": "package-lock.json",
    }

    def test_aliases_stored_as_list(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, [self._OSV_FINDING])
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        aliases = results[0]["metadata"].get("aliases")
        assert isinstance(aliases, list)
        assert len(aliases) == 2

    def test_null_meta_does_not_cause_error(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            [
                {
                    "tool": "osv-scanner",
                    "package_name": "pkg",
                    "vulnerability_id": "GHSA-y",
                    "ecosystem": "PyPI",
                }
            ],
        )
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert len(results) == 1
        assert results[0]["metadata"].get("tool") == "osv-scanner"
