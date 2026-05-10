"""Integration tests for SQLite store purge operations."""

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


def _seed_all(store: _TestStore) -> int:
    run_id = store.create_run({"args": []})
    all_findings = (
        _SEMGREP_FINDINGS + _GITLEAKS_FINDINGS + _NMAP_FINDINGS + _ZAP_FINDINGS
    )
    store.insert_findings(run_id, all_findings)
    return run_id


class TestPurge:
    def test_purge_all_clears_findings(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=None)

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results == []

    def test_purge_all_clears_runs(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=None)

        conn = store._connect()
        assert conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0] == 0

    def test_purge_tool_only_removes_that_tool(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=["semgrep"])

        remaining = store.search({"conditions": [], "page": 1, "page_size": 200})
        tools = {r["metadata"]["tool"] for r in remaining}
        assert "semgrep" not in tools
        assert "gitleaks" in tools
        assert "nmap" in tools

    def test_purge_tool_keeps_runs(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        _seed_all(store)

        store.delete_findings(tools=["gitleaks"])

        conn = store._connect()
        count = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        assert count >= 1

    def test_purge_all_clears_triage_batches(self, tmp_path: Path) -> None:
        """Full purge must delete all triage_batches records."""
        import json

        store = _make_store(tmp_path)
        run_id = _seed_all(store)

        conn = store._connect()
        conn.execute(
            "INSERT INTO triage_batches (run_id, finding_ids, batch_data, status) "
            "VALUES (?, ?, ?, ?)",
            (run_id, json.dumps([1]), "[]", "pending"),
        )
        conn.commit()
        conn.close()

        store.delete_findings(tools=None)

        conn = store._connect()
        assert conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[0] == 0
        conn.close()

    def test_purge_all_clears_tool_audit_log(self, tmp_path: Path) -> None:
        """Full purge must delete all tool_audit_log records."""
        store = _make_store(tmp_path)
        _seed_all(store)

        conn = store._connect()
        conn.execute(
            "INSERT INTO tool_audit_log (tool_name, arguments, called_at) "
            "VALUES (?, ?, datetime('now'))",
            ("semgrep", "{}"),
        )
        conn.commit()
        conn.close()

        store.delete_findings(tools=None)

        conn = store._connect()
        assert conn.execute("SELECT COUNT(*) FROM tool_audit_log").fetchone()[0] == 0
        conn.close()

    def test_purge_all_clears_run_tools(self, tmp_path: Path) -> None:
        """Full purge must delete all run_tools records."""
        store = _make_store(tmp_path)
        run_id = _seed_all(store)

        conn = store._connect()
        conn.execute(
            "INSERT INTO run_tools (run_id, tool, findings_count) VALUES (?, ?, ?)",
            (run_id, "semgrep", 2),
        )
        conn.commit()
        conn.close()

        store.delete_findings(tools=None)

        conn = store._connect()
        assert conn.execute("SELECT COUNT(*) FROM run_tools").fetchone()[0] == 0
        conn.close()

    def test_purge_tool_clears_triage_batches_for_tool(self, tmp_path: Path) -> None:
        """Tool-specific purge deletes triage_batches that only reference that tool."""
        import json

        store = _make_store(tmp_path)
        run_id = _seed_all(store)

        conn = store._connect()
        semgrep_id = conn.execute(
            "SELECT id FROM findings WHERE tool = 'semgrep' LIMIT 1"
        ).fetchone()["id"]
        gitleaks_id = conn.execute(
            "SELECT id FROM findings WHERE tool = 'gitleaks' LIMIT 1"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO triage_batches (run_id, finding_ids, batch_data, status) "
            "VALUES (?, ?, ?, ?)",
            (run_id, json.dumps([semgrep_id]), "[]", "pending"),
        )
        conn.execute(
            "INSERT INTO triage_batches (run_id, finding_ids, batch_data, status) "
            "VALUES (?, ?, ?, ?)",
            (run_id, json.dumps([gitleaks_id]), "[]", "pending"),
        )
        conn.commit()
        conn.close()

        store.delete_findings(tools=["semgrep"])

        conn = store._connect()
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM findings WHERE tool = 'semgrep'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM findings WHERE tool = 'gitleaks'"
            ).fetchone()[0]
            > 0
        )
        # Semgrep batch deleted, gitleaks batch preserved
        assert conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[0] == 1
        conn.close()

    def test_purge_tool_clears_tool_audit_log_for_tool(self, tmp_path: Path) -> None:
        """Tool-specific purge deletes tool_audit_log only for that tool."""
        store = _make_store(tmp_path)
        _seed_all(store)

        conn = store._connect()
        conn.execute(
            "INSERT INTO tool_audit_log (tool_name, arguments, called_at) "
            "VALUES (?, ?, datetime('now'))",
            ("semgrep", "{}"),
        )
        conn.execute(
            "INSERT INTO tool_audit_log (tool_name, arguments, called_at) "
            "VALUES (?, ?, datetime('now'))",
            ("gitleaks", "{}"),
        )
        conn.commit()
        conn.close()

        store.delete_findings(tools=["semgrep"])

        conn = store._connect()
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM tool_audit_log WHERE tool_name = 'semgrep'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM tool_audit_log WHERE tool_name = 'gitleaks'"
            ).fetchone()[0]
            == 1
        )
        conn.close()

    def test_purge_mixed_batch_preserved(self, tmp_path: Path) -> None:
        """Triage batch referencing multiple tools is kept on single-tool purge."""
        import json

        store = _make_store(tmp_path)
        run_id = _seed_all(store)

        conn = store._connect()
        semgrep_id = conn.execute(
            "SELECT id FROM findings WHERE tool = 'semgrep' LIMIT 1"
        ).fetchone()["id"]
        gitleaks_id = conn.execute(
            "SELECT id FROM findings WHERE tool = 'gitleaks' LIMIT 1"
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO triage_batches (run_id, finding_ids, batch_data, status) "
            "VALUES (?, ?, ?, ?)",
            (run_id, json.dumps([semgrep_id, gitleaks_id]), "[]", "pending"),
        )
        conn.commit()
        conn.close()

        store.delete_findings(tools=["semgrep"])

        conn = store._connect()
        # Batch has a gitleaks finding still present; must not be deleted
        assert conn.execute("SELECT COUNT(*) FROM triage_batches").fetchone()[0] == 1
        conn.close()

    def test_schema_recreated_after_db_delete(self, tmp_path: Path) -> None:
        """After deleting and recreating the DB, _init_schema works cleanly."""
        store = _make_store(tmp_path)
        _seed_all(store)

        # Simulate full purge: delete file then reinit
        store._db_path.unlink()
        store._init_schema()

        results = store.search({"conditions": [], "page": 1, "page_size": 200})
        assert results == []
