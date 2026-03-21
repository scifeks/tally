"""Integration tests for findings.get_finding()."""

from __future__ import annotations

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tally_mcp.tools import findings
from tests.integration.mcp.conftest import _first_id, _seed


async def test_get_finding_returns_parsed_dict(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert isinstance(row, dict)
    assert isinstance(row["meta"], dict)
    assert isinstance(row["finding_type"], list)


async def test_get_finding_unknown_id_raises_value_error(
    store: ConnectionFactory,
    finding_repo: FindingRepository,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await findings.get_finding(999_999)


async def test_null_severity_confidence_returned_as_none(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
) -> None:
    _seed(run_repo, finding_repo, {"severity": None, "confidence": None})
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert row["severity"] is None
    assert row["confidence"] is None


async def test_get_finding_includes_abs_path(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    row = await findings.get_finding(fid)
    assert "abs_path" in row
