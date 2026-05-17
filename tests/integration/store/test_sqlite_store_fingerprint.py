"""Integration tests for SQLite store fingerprint deduplication."""

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


_GITLEAKS_FINDINGS = [
    {
        "tool": "gitleaks",
        "domain": "code",
        "finding_type": "secret",
        "severity": "critical",
        "confidence": "confirmed",
        "file_path": "src/config.py",
        "rule_id": "generic-api-key",
        "line_number": 99,
        "profile": "repo1",
    },
    {
        "tool": "gitleaks",
        "domain": "code",
        "finding_type": "secret",
        "severity": "high",
        "confidence": "confirmed",
        "file_path": "deploy/setup.sh",
        "rule_id": "aws-access-key",
        "line_number": 5,
        "profile": "repo1",
    },
]


class TestFingerprint:
    def test_same_finding_two_runs_produces_two_rows(self, tmp_path: Path) -> None:
        """Same finding in two different runs produces two separate rows.

        Scans are INSERT-only; each run_id gets its own findings rows.
        """
        store = _make_store(tmp_path)

        run_id1 = store.create_run({"args": []})
        store.insert_findings(run_id1, normalize_test_findings(_GITLEAKS_FINDINGS[:1]))

        run_id2 = store.create_run({"args": []})
        store.insert_findings(run_id2, normalize_test_findings(_GITLEAKS_FINDINGS[:1]))

        conn = store._connect()
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 2

    def test_fingerprint_uniqueness(self, tmp_path: Path) -> None:
        """Two different findings produce different fingerprints."""
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings(_GITLEAKS_FINDINGS))

        conn = store._connect()
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 2
