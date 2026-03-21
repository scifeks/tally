"""Integration tests for SQLite store description field."""

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

    def upsert_findings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._finding_repo.upsert_findings(*args, **kwargs)  # type: ignore[attr-defined]

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


class TestDescription:
    def test_zap_description_set(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(
            run_id,
            [
                {
                    "tool": "zap",
                    "url": "https://example.com",
                    "alert_name": "sqli",
                    "description": "SQL injection in login form",
                }
            ],
        )
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("description") == (
            "SQL injection in login form"
        )

    def test_semgrep_description_equals_message(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(
            run_id,
            [
                {
                    "tool": "semgrep",
                    "rule_id": "r1",
                    "file_path": "a.py",
                    "line_start": 1,
                    "description": "Use of eval is dangerous",
                }
            ],
        )
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("description") == "Use of eval is dangerous"

    def test_sca_description_from_summary(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(
            run_id,
            [
                {
                    "tool": "pip-audit",
                    "package_name": "pkg",
                    "vulnerability_id": "GHSA-y",
                    "description": "Remote code execution via deserialization",
                }
            ],
        )
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("description") == (
            "Remote code execution via deserialization"
        )

    def test_gitleaks_description_set_when_present(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.upsert_findings(
            run_id,
            [
                {
                    "tool": "gitleaks",
                    "rule_id": "generic-api-key",
                    "file_path": "config.py",
                    "line_number": 10,
                    "description": "Generic API Key",
                }
            ],
        )
        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results[0]["metadata"].get("description") == "Generic API Key"
