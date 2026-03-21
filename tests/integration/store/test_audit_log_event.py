"""Tests for AuditRepository.log_event."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

import pytest  # noqa: E402

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.audit import AuditRepository  # noqa: E402

pytestmark = pytest.mark.integration


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
