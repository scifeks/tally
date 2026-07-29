"""Tests for upsert should_report default and batch analyst field updates."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from tests.finding_helpers import normalize_test_findings  # noqa: E402

pytestmark = pytest.mark.integration

_BASE_FINDING: dict = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "file_path": "src/app.py",
    "rule_id": "test-rule",
    "description": "test finding",
    "segment": "sast",
    "repo": "test-repo",
}


class TestUpsertShouldReportDefault:
    def test_insert_findings_sets_should_report_to_0(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)
        run_id = run_repo.create_run({})
        finding_repo.insert_findings(run_id, normalize_test_findings([_BASE_FINDING]))
        with factory.connect() as conn:
            row = conn.execute("SELECT should_report FROM findings LIMIT 1").fetchone()
        assert row["should_report"] == 0

    def test_rescan_dedup_preserves_prior_approval(self, tmp_path: Path) -> None:
        """A rescan deduplicates by fingerprint, preserving approval.

        When the same finding appears in a later run, the existing row
        is updated (run_id, last_seen, seen_count) but should_report
        and other triage fields are not touched.
        """
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)

        run_id1 = run_repo.create_run({})
        finding_repo.insert_findings(run_id1, normalize_test_findings([_BASE_FINDING]))
        with factory.connect() as conn:
            conn.execute(
                "UPDATE findings SET should_report = 1 WHERE run_id = ?",
                (run_id1,),
            )

        run_id2 = run_repo.create_run({})
        finding_repo.insert_findings(run_id2, normalize_test_findings([_BASE_FINDING]))

        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT run_id, should_report, seen_count FROM findings"
            ).fetchall()

        assert len(rows) == 1
        assert rows[0]["run_id"] == run_id2
        assert rows[0]["should_report"] == 1
        assert rows[0]["seen_count"] == 2


class TestBatchUpdateAnalystFields:
    def _seed(
        self, tmp_path: Path, count: int = 2
    ) -> tuple[ConnectionFactory, list[int]]:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)
        run_id = run_repo.create_run({})
        findings = [
            {**_BASE_FINDING, "rule_id": f"rule-{i}", "file_path": f"src/{i}.py"}
            for i in range(count)
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))
        with factory.connect() as conn:
            ids = [
                r["id"]
                for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
            ]
        return factory, ids

    def test_updates_all_ids_in_batch(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path, count=3)
        finding_repo = FindingRepository(factory)
        updated = finding_repo.batch_update_analyst_fields(ids, {"should_report": 1})
        assert updated == 3
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT should_report FROM findings ORDER BY id"
            ).fetchall()
        assert all(r["should_report"] == 1 for r in rows)

    def test_sets_triaged_by_and_triaged_at(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path)
        finding_repo = FindingRepository(factory)
        finding_repo.batch_update_analyst_fields(ids, {"should_report": 1})
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings ORDER BY id"
            ).fetchall()
        for row in rows:
            assert row["triaged_by"] == "analyst_web"
            assert row["triaged_at"] is not None

    def test_returns_count_of_updated_rows(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path, count=3)
        finding_repo = FindingRepository(factory)
        # Pass only 2 of 3 IDs
        updated = finding_repo.batch_update_analyst_fields(
            ids[:2], {"should_report": 1}
        )
        assert updated == 2

    def test_nonexistent_ids_are_silently_skipped(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path, count=2)
        finding_repo = FindingRepository(factory)
        updated = finding_repo.batch_update_analyst_fields(
            [99999, 99998], {"should_report": 1}
        )
        assert updated == 0

    def test_empty_ids_returns_zero(self, tmp_path: Path) -> None:
        factory, _ = self._seed(tmp_path)
        finding_repo = FindingRepository(factory)
        updated = finding_repo.batch_update_analyst_fields([], {"should_report": 1})
        assert updated == 0
