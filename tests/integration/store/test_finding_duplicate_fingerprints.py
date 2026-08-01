"""Tests that duplicate fingerprints in the same run produce separate rows.

Validates the npm-audit ``tar/CVE-2021-32804`` scenario: two distinct
advisory entries in the same audit output share identical
(package_name, vulnerability_id) and therefore produce the same
fingerprint.  With plain INSERT semantics both rows must be stored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.finding_helpers import normalize_test_findings

pytestmark = pytest.mark.integration

_FINDING_A = {
    "tool": "npm-audit",
    "domain": "sca",
    "segment": "sca",
    "package_name": "tar",
    "vulnerability_id": "CVE-2021-32804",
    "ecosystem": "npm",
    "severity": "high",
    "description": "tar advisory entry 1",
}

_FINDING_B = {
    "tool": "npm-audit",
    "domain": "sca",
    "segment": "sca",
    "package_name": "tar",
    "vulnerability_id": "CVE-2021-32804",
    "ecosystem": "npm",
    "severity": "high",
    "description": "tar advisory entry 2",
}


class TestDuplicateFingerprintsInSameRun:
    def test_two_findings_same_fingerprint_same_run(self, tmp_path: Path) -> None:
        """Two findings with identical fingerprints in one run → two rows.

        This is the npm-audit case where a single CVE appears in two
        separate advisory entries.  Both must be persisted.
        """
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)

        run_id = run_repo.create_run({})
        finding_repo.insert_findings(
            run_id, normalize_test_findings([_FINDING_A, _FINDING_B])
        )

        with factory.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE run_id = ?", (run_id,)
            ).fetchone()[0]

        assert count == 2

    def test_same_fingerprint_across_runs_creates_separate_rows(
        self, tmp_path: Path
    ) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)

        run_id1 = run_repo.create_run({})
        finding_repo.insert_findings(run_id1, normalize_test_findings([_FINDING_A]))

        run_id2 = run_repo.create_run({})
        finding_repo.insert_findings(run_id2, normalize_test_findings([_FINDING_A]))

        with factory.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            run_ids = [
                r["run_id"]
                for r in conn.execute(
                    "SELECT run_id FROM findings ORDER BY id"
                ).fetchall()
            ]

        assert count == 2
        assert run_ids == [run_id1, run_id2]

    def test_repeated_insert_same_run_appends(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)

        run_id = run_repo.create_run({})
        finding_repo.insert_findings(run_id, normalize_test_findings([_FINDING_A]))
        finding_repo.insert_findings(run_id, normalize_test_findings([_FINDING_A]))

        with factory.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]

        assert count == 2
