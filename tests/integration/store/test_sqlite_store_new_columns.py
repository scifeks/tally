"""Integration tests for SQLite store new named columns."""

from __future__ import annotations

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


class TestNewColumns:
    _SCA_FINDING = {
        "tool": "pip-audit",
        "domain": "sca",
        "finding_type": '["dependency"]',
        "severity": "high",
        "package_name": "requests",
        "package_version": "2.27.0",
        "vulnerability_id": "GHSA-1234",
        "ecosystem": "PyPI",
        "lockfile": "requirements.txt",
        "cwe_ids": "CWE-400, CWE-20",
        "profile": "repo1",
    }

    def test_file_populated_from_lockfile(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings([self._SCA_FINDING]))
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("file_path") == "requirements.txt"

    def test_package_version_populated(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings([self._SCA_FINDING]))
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("package_version") == "2.27.0"

    def test_package_name_populated(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings([self._SCA_FINDING]))
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("package_name") == "requests"

    def test_cwe_is_list(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings([self._SCA_FINDING]))
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        cwe = results[0]["metadata"].get("cwe")
        assert isinstance(cwe, list)
        assert len(cwe) == 2

    def test_file_path_takes_priority_over_lockfile(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        finding = dict(self._SCA_FINDING)
        finding["file_path"] = "src/requirements.txt"
        store.insert_findings(run_id, normalize_test_findings([finding]))
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("file_path") == "src/requirements.txt"
