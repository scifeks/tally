"""Integration tests for findings.update_finding() persistence."""

from __future__ import annotations

import json

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.audit import AuditRepository
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository
from tally_mcp.context import FindingsContext
from tally_mcp.tools import findings
from tests.integration.mcp.conftest import _VALID_UPDATE, _first_id, _seed


async def test_valid_update_returns_true_and_persists(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    result = await findings.update_finding(fid, **_VALID_UPDATE)
    assert result is True

    with store.connect() as conn:
        db_row = conn.execute("SELECT * FROM findings WHERE id = ?", (fid,)).fetchone()

    assert db_row["confidence"] == "probable"
    assert db_row["severity"] == 1
    assert db_row["enriched"] == 1
    assert db_row["triaged_by"] == "claudecode"
    assert db_row["triaged_at"] is not None

    ft = json.loads(db_row["finding_type"])
    assert isinstance(ft, list)
    assert ft == ["vulnerability"]

    meta = json.loads(db_row["meta"])
    triage = meta["triage"]
    assert triage["confidence"] == "probable"
    assert triage["strategy"] == "manual"
    assert triage["triaged_by"] == "claudecode"
    assert "triaged_at" in triage


async def test_previous_confidence_tracked_across_updates(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    _seed(run_repo, finding_repo)  # initial confidence = "medium"
    fid = _first_id(store)

    # First update: medium → probable
    await findings.update_finding(fid, **{**_VALID_UPDATE, "confidence": "probable"})
    # Second update: probable → confirmed
    await findings.update_finding(fid, **{**_VALID_UPDATE, "confidence": "confirmed"})

    with store.connect() as conn:
        db_row = conn.execute(
            "SELECT meta FROM findings WHERE id = ?", (fid,)
        ).fetchone()

    meta = json.loads(db_row["meta"])
    assert meta["triage"]["previous_confidence"] == "probable"
    assert meta["triage"]["confidence"] == "confirmed"


async def test_triaged_by_can_be_overridden_for_opencode(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
    triage_repo: TriageBatchRepository,
    monkeypatch,
) -> None:
    _seed(run_repo, finding_repo)
    fid = _first_id(store)
    monkeypatch.setenv("TALLY_TRIAGED_BY", "opencode")
    findings.init(
        FindingsContext(
            finding_repo=finding_repo,
            audit_repo=audit_repo,
            triage_repo=triage_repo,
            project_name="",
        )
    )

    try:
        result = await findings.update_finding(fid, **_VALID_UPDATE)
        assert result is True

        with store.connect() as conn:
            db_row = conn.execute(
                "SELECT triaged_by, meta FROM findings WHERE id = ?", (fid,)
            ).fetchone()

        assert db_row["triaged_by"] == "opencode"
        triage = json.loads(db_row["meta"])["triage"]
        assert triage["triaged_by"] == "opencode"
    finally:
        monkeypatch.delenv("TALLY_TRIAGED_BY", raising=False)
        findings.init(
            FindingsContext(
                finding_repo=finding_repo,
                audit_repo=audit_repo,
                triage_repo=triage_repo,
                project_name="",
            )
        )
