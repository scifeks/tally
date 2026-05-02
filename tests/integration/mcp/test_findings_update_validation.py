"""Integration tests for findings.update_finding() enum validation."""

from __future__ import annotations

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.audit import AuditRepository
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tally_mcp.tools import findings
from tests.integration.mcp.conftest import (
    _BASE_FINDING,
    _VALID_UPDATE,
    _first_id,
    _seed,
)


async def test_invalid_confidence_raises(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid confidence"):
        await findings.update_finding(
            fid, **{**_VALID_UPDATE, "confidence": "definitely"}
        )
    # DB row unchanged
    row = await findings.get_finding(fid)
    assert row["confidence"] == _BASE_FINDING["confidence"]


async def test_invalid_severity_raises(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid severity"):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "severity": "extreme"})
    row = await findings.get_finding(fid)
    assert row["severity"] == _BASE_FINDING["severity"]


async def test_invalid_finding_type_raises(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    with pytest.raises(ValueError, match="Invalid finding_type"):
        await findings.update_finding(fid, **{**_VALID_UPDATE, "finding_type": "ghost"})
    db_row = await findings.get_finding(fid)
    assert db_row["finding_type"] == [_BASE_FINDING["finding_type"]]


async def test_false_positive_confidence_accepted(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    result = await findings.update_finding(
        fid, **{**_VALID_UPDATE, "confidence": "false_positive"}
    )
    assert result is True
    row = await findings.get_finding(fid)
    assert row["confidence"] == "false_positive"


async def test_nonexistent_finding_id_raises(
    store: ConnectionFactory,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await findings.update_finding(999_999, **_VALID_UPDATE)
