"""Integration tests for SQLite store pagination."""

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


_SEMGREP_FINDINGS = [
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "high",
        "confidence": "probable",
        "file_path": "config/app.py",
        "rule_id": "python.sql-injection",
        "line_start": 42,
        "profile": "repo1",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "medium",
        "confidence": "potential",
        "file_path": "web/index.php",
        "rule_id": "php.xss",
        "line_start": 10,
        "profile": "repo1",
    },
]

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

_NMAP_FINDINGS = [
    {
        "tool": "nmap",
        "domain": "network",
        "finding_type": "informational",
        "severity": "informational",
        "confidence": "confirmed",
        "ip_address": "192.168.1.1",
        "port": "22",
        "service": "ssh",
        "transport": "tcp",
        "profile": "production",
    },
]

_ZAP_FINDINGS = [
    {
        "tool": "zap",
        "domain": "web",
        "finding_type": "vulnerability",
        "severity": "high",
        "confidence": "probable",
        "url": "https://example.com/login",
        "method": "POST",
        "param": "user_id",
        "alert_name": "sql_injection",
        "risk_type": "sql_injection",
        "profile": "repo1",
    },
    {
        "tool": "zap",
        "domain": "web",
        "finding_type": "vulnerability",
        "severity": "medium",
        "confidence": "probable",
        "url": "https://example.com/search",
        "method": "GET",
        "param": "q",
        "alert_name": "xss_reflected",
        "risk_type": "xss_reflected",
        "profile": "repo1",
    },
]


class TestPagination:
    def test_page_two_returns_correct_slice(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        # Seed 7 findings (2 semgrep + 2 gitleaks + 1 nmap + 2 zap)
        store.insert_findings(
            run_id,
            normalize_test_findings(
                _SEMGREP_FINDINGS + _GITLEAKS_FINDINGS + _NMAP_FINDINGS + _ZAP_FINDINGS
            ),
        )

        page1 = store.search({"conditions": [], "page": 1, "page_size": 5})
        page2 = store.search({"conditions": [], "page": 2, "page_size": 5})

        assert len(page1) == 5
        # Total = 7, so page 2 has 2 rows
        assert len(page2) == 2

    def test_page_one_and_two_no_overlap(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(
            run_id,
            normalize_test_findings(
                _SEMGREP_FINDINGS + _GITLEAKS_FINDINGS + _NMAP_FINDINGS + _ZAP_FINDINGS
            ),
        )

        p1_rules = [
            r["metadata"].get("rule_id")
            for r in store.search({"conditions": [], "page": 1, "page_size": 4})
        ]
        p2_rules = [
            r["metadata"].get("rule_id")
            for r in store.search({"conditions": [], "page": 2, "page_size": 4})
        ]
        # No row should appear in both pages
        assert not set(p1_rules) & set(p2_rules)

    def test_empty_second_page(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        run_id = store.create_run({})
        store.insert_findings(run_id, normalize_test_findings(_NMAP_FINDINGS))

        page2 = store.search({"conditions": [], "page": 2, "page_size": 200})
        assert page2 == []
