"""Tests for duplicate_of IS NULL filter in direct-SQL read paths."""

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


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


def _make_test_finding(
    tool: str = "semgrep",
    severity: str = "high",
    rule_id: str = "r1",
    line_start: int = 10,
) -> dict:
    return {
        "tool": tool,
        "segment": "sast",
        "file_path": "src/test.py",
        "rule_id": rule_id,
        "severity": severity,
        "risk_type": "injection",
        "line_start": line_start,
    }


def test_get_all_findings_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """get_all_findings excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1", line_start=10),
        _make_test_finding(rule_id="r2", line_start=20),
        _make_test_finding(rule_id="r3", line_start=30),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]
    assert len(finding_ids) == 3

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    rows_after = finding_repo.get_all_findings()
    row_ids_after = [r.id for r in rows_after]

    assert len(row_ids_after) == 2
    assert loser_id not in row_ids_after
    assert survivor_id in row_ids_after
    assert finding_ids[2] in row_ids_after


def test_get_findings_by_run_id_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """get_findings_by_run_id excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1", line_start=10),
        _make_test_finding(rule_id="r2", line_start=20),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_findings_by_run_id(run_id)
    finding_ids = [r.id for r in rows]
    assert len(finding_ids) == 2

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    rows_after = finding_repo.get_findings_by_run_id(run_id)
    row_ids_after = [r.id for r in rows_after]

    assert len(row_ids_after) == 1
    assert loser_id not in row_ids_after
    assert survivor_id in row_ids_after


def test_get_reportable_findings_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """get_reportable_findings excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1", line_start=10),
        _make_test_finding(rule_id="r2", line_start=20),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET should_report = 1 WHERE id IN (?, ?)",
            (survivor_id, loser_id),
        )
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    rows_after = finding_repo.get_reportable_findings()
    row_ids_after = [r.id for r in rows_after]

    assert len(row_ids_after) == 1
    assert loser_id not in row_ids_after
    assert survivor_id in row_ids_after


def test_get_all_findings_deserialized_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """get_all_findings_deserialized excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1", line_start=10),
        _make_test_finding(rule_id="r2", line_start=20),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]
    rule_ids = [r.rule_id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]
    loser_rule_id = rule_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    rows_after = finding_repo.get_all_findings_deserialized()
    rule_ids_after = [r["rule_id"] for r in rows_after]

    assert len(rows_after) == 1
    assert loser_rule_id not in rule_ids_after
    assert "r1" in rule_ids_after


def test_get_reportable_findings_deserialized_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """get_reportable_findings_deserialized excludes duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1", line_start=10),
        _make_test_finding(rule_id="r2", line_start=20),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]
    rule_ids = [r.rule_id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]
    loser_rule_id = rule_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET should_report = 1 WHERE id IN (?, ?)",
            (survivor_id, loser_id),
        )
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    rows_after = finding_repo.get_reportable_findings_deserialized()
    rule_ids_after = [r["rule_id"] for r in rows_after]

    assert len(rows_after) == 1
    assert loser_rule_id not in rule_ids_after
    assert "r1" in rule_ids_after


def test_count_aggregates_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """count_aggregates excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1", severity="high"),
        _make_test_finding(rule_id="r2", severity="high"),
        _make_test_finding(rule_id="r3", severity="medium"),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    agg_after = finding_repo.count_aggregates()

    assert agg_after["total"] == 2
    assert agg_after["by_severity"].get("high") == 1
    assert agg_after["by_severity"].get("medium") == 1


def test_distinct_facet_values_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """distinct_facet_values excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1"),
        _make_test_finding(rule_id="r2"),
        _make_test_finding(rule_id="r3"),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    facets_after = finding_repo.distinct_facet_values()

    assert len(facets_after["tools"]) == 1
    assert "semgrep" in facets_after["tools"]


def test_get_findings_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """get_findings excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1"),
        _make_test_finding(rule_id="r2"),
        _make_test_finding(rule_id="r3"),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    rows_after = finding_repo.get_findings()
    row_ids_after = [r.id for r in rows_after]

    assert loser_id not in row_ids_after
    assert survivor_id in row_ids_after


def test_count_findings_excludes_duplicates(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    run_repo: RunRepository,
) -> None:
    """count_findings excludes rows with duplicate_of IS NOT NULL."""
    run_id = run_repo.create_run({})

    findings = [
        _make_test_finding(rule_id="r1"),
        _make_test_finding(rule_id="r2"),
        _make_test_finding(rule_id="r3"),
    ]
    finding_repo.insert_findings(run_id, normalize_test_findings(findings))

    rows = finding_repo.get_all_findings()
    finding_ids = [r.id for r in rows]

    survivor_id = finding_ids[0]
    loser_id = finding_ids[1]

    with factory.connect() as conn:
        conn.execute(
            "UPDATE findings SET duplicate_of = ? WHERE id = ?",
            (survivor_id, loser_id),
        )

    count_after = finding_repo.count_findings()

    assert count_after == 2


class TestInsertFindingsShouldReport:
    def test_insert_findings_with_should_report_true(
        self,
        factory: ConnectionFactory,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """insert_findings respects should_report=True parameter."""
        run_id = run_repo.create_run({})
        findings = [_make_test_finding(rule_id="r1")]
        finding_repo.insert_findings(
            run_id, normalize_test_findings(findings), should_report=True
        )

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT should_report FROM findings WHERE rule_id = 'r1'"
            ).fetchone()

        assert row["should_report"] == 1

    def test_insert_findings_default_should_report_false(
        self,
        factory: ConnectionFactory,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """insert_findings defaults should_report to 0 when not specified."""
        run_id = run_repo.create_run({})
        findings = [_make_test_finding(rule_id="r2")]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT should_report FROM findings WHERE rule_id = 'r2'"
            ).fetchone()

        assert row["should_report"] == 0


class TestMarkAsDuplicate:
    def test_mark_as_duplicate_sets_duplicate_of(
        self,
        factory: ConnectionFactory,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """mark_as_duplicate sets duplicate_of on the loser finding."""
        run_id = run_repo.create_run({})

        findings = [
            _make_test_finding(rule_id="r1"),
            _make_test_finding(rule_id="r2"),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        rows = finding_repo.get_all_findings()
        finding_ids = [r.id for r in rows]
        survivor_id = finding_ids[0]
        loser_id = finding_ids[1]

        finding_repo.mark_as_duplicate(loser_id, survivor_id)

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT duplicate_of FROM findings WHERE id = ?",
                (loser_id,),
            ).fetchone()

        assert row["duplicate_of"] == survivor_id

    def test_mark_as_duplicate_no_op_for_nonexistent_finding(
        self,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """mark_as_duplicate silently succeeds for nonexistent finding id."""
        run_id = run_repo.create_run({})

        findings = [_make_test_finding(rule_id="r1")]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        count_before = finding_repo.count_findings()

        finding_repo.mark_as_duplicate(999, 100)

        count_after = finding_repo.count_findings()

        assert count_before == count_after
