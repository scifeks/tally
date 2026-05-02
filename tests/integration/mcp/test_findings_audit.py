"""Integration tests for findings audit log written on every call."""

from __future__ import annotations

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.audit import AuditRepository
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tally_mcp.tools import findings
from tests.integration.mcp.conftest import _VALID_UPDATE, _first_id, _seed


async def test_audit_written_on_success(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    await findings.update_finding(fid, **_VALID_UPDATE)

    with store.connect() as conn:
        row = conn.execute(
            "SELECT tool_name, success, duration_ms FROM tool_audit_log"
            " WHERE tool_name = 'update_finding'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["success"] == 1
    assert row["duration_ms"] >= 0


async def test_audit_written_on_validation_failure(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "severity": "unknown"})

    with store.connect() as conn:
        row = conn.execute(
            "SELECT success FROM tool_audit_log"
            " WHERE tool_name = 'update_finding'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["success"] == 0
