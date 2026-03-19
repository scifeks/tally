"""Tests for AuditRepository."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

import pytest  # noqa: E402

from core.store.connection import ConnectionFactory  # noqa: E402
from core.store.repositories.audit import AuditRepository  # noqa: E402


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> AuditRepository:
    return AuditRepository(factory)


class TestLogEvent:
    def test_inserts_row(
        self, factory: ConnectionFactory, repo: AuditRepository
    ) -> None:
        repo.log_event("update_finding", {"finding_id": 1}, True, None, 42)
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tool_audit_log WHERE tool_name = 'update_finding'"
            ).fetchone()
        assert row is not None
        assert row["success"] == 1
        assert row["duration_ms"] == 42
        assert row["error"] is None

    def test_failure_stored(
        self, factory: ConnectionFactory, repo: AuditRepository
    ) -> None:
        repo.log_event("update_finding", {}, False, "validation error", 10)
        with factory.connect() as conn:
            row = conn.execute("SELECT success, error FROM tool_audit_log").fetchone()
        assert row["success"] == 0
        assert row["error"] == "validation error"

    def test_called_at_populated(
        self, factory: ConnectionFactory, repo: AuditRepository
    ) -> None:
        repo.log_event("get_findings_batch", {}, True, None, 5)
        with factory.connect() as conn:
            row = conn.execute("SELECT called_at FROM tool_audit_log").fetchone()
        assert row["called_at"] is not None


class TestCountEventsSince:
    def test_counts_matching_rows(self, repo: AuditRepository) -> None:
        from datetime import UTC, datetime

        before = datetime.now(UTC).isoformat()
        repo.log_event("update_finding", {}, True, None, 1)
        repo.log_event("update_finding", {}, True, None, 2)
        count = repo.count_events_since(("update_finding",), before)
        assert count == 2

    def test_excludes_rows_before_cutoff(self, repo: AuditRepository) -> None:
        repo.log_event("update_finding", {}, True, None, 1)
        from datetime import UTC, datetime

        after = datetime.now(UTC).isoformat()
        count = repo.count_events_since(("update_finding",), after)
        assert count == 0

    def test_filters_by_tool_name(self, repo: AuditRepository) -> None:
        from datetime import UTC, datetime

        before = datetime.now(UTC).isoformat()
        repo.log_event("update_finding", {}, True, None, 1)
        repo.log_event("get_findings_batch", {}, True, None, 1)
        count = repo.count_events_since(("update_finding",), before)
        assert count == 1
