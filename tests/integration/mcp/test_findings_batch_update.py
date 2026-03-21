"""Integration tests for findings.update_findings_batch()."""

from __future__ import annotations

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.audit import AuditRepository
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tally_mcp.tools import findings
from tests.integration.mcp.conftest import _BASE_FINDING, _VALID_UPDATE


async def test_update_findings_batch_mixed(
    store: ConnectionFactory,
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
) -> None:
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(
        run_id,
        [
            {**_BASE_FINDING, "rule_id": "rule-a", "file_path": "src/a.py"},
            {**_BASE_FINDING, "rule_id": "rule-b", "file_path": "src/b.py"},
        ],
    )
    with store.connect() as conn:
        ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
        ]
    fid_valid, fid_bad = ids[0], ids[1]

    updates = [
        {"finding_id": fid_valid, **_VALID_UPDATE},
        {"finding_id": fid_bad, **{**_VALID_UPDATE, "confidence": "bogus"}},
    ]
    result = await findings.update_findings_batch(updates)

    assert result[str(fid_valid)]["status"] == "updated"
    assert result[str(fid_bad)]["status"] == "error"

    row = await findings.get_finding(fid_valid)
    assert row["confidence"] == "probable"
