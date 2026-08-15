"""Integration tests for McpIngestService.get_duplicate_candidates."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.mcp.ingest_service import McpIngestService
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.finding_helpers import normalize_test_findings

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


@pytest.fixture()
def run_id(run_repo: RunRepository) -> int:
    return run_repo.create(
        project_id=1,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
    )


def _make_test_finding(
    file: str = "src/test.py",
    rule_id: str = "xss.stored",
    line_number: int = 10,
    line_end: int | None = None,
) -> dict:
    """Create a test finding dict."""
    result = {
        "tool": "semgrep",
        "segment": "sast",
        "file_path": file,
        "rule_id": rule_id,
        "severity": "high",
        "line_number": line_number,
    }
    if line_end is not None:
        result["line_end"] = line_end
    return result


class TestGetDuplicateCandidatesEmptyRun:
    def test_empty_run_returns_empty_groups(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Empty run (no findings) returns {"groups": []}."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert result == {"groups": []}


class TestGetDuplicateCandidatesSameFileFamily:
    def test_two_findings_same_file_same_family_overlapping_lines(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Two findings same file, same family (xss.stored, xss.reflected),
        overlapping lines -> one group of two returned.
        """
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
                line_end=15,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=12,
                line_end=18,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert "groups" in result
        assert len(result["groups"]) == 1
        assert len(result["groups"][0]) == 2
        # IDs should be sorted within the group
        assert result["groups"][0] == sorted(result["groups"][0])

    def test_two_findings_same_file_same_family_within_proximity(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Two findings same file, same family, but lines 5 apart -> grouped."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=14,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert len(result["groups"]) == 1
        assert len(result["groups"][0]) == 2


class TestGetDuplicateCandidatesDifferentFamilies:
    def test_two_findings_same_file_different_families(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Two findings same file, different families (xss, injection) -> no groups."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="injection.sql",
                line_number=15,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert result["groups"] == []


class TestGetDuplicateCandidatesDifferentFiles:
    def test_two_findings_different_files(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Two findings different files -> no groups."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
            ),
            _make_test_finding(
                file="src/other.py",
                rule_id="xss.stored",
                line_number=10,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert result["groups"] == []


class TestGetDuplicateCandidatesProximityBoundary:
    def test_two_findings_far_apart_beyond_proximity(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Two findings same file, same family, but lines 20+ apart -> no groups."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=35,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert result["groups"] == []


class TestGetDuplicateCandidatesMultipleGroups:
    def test_three_findings_two_groups(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Three findings with two separate groups."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=12,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=40,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        assert len(result["groups"]) == 1
        # Findings 1 and 2 group together (within proximity)
        # Finding 3 is alone because it's too far
        assert len(result["groups"][0]) == 2


class TestGetDuplicateCandidatesLineRanges:
    def test_findings_with_explicit_line_end(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Findings with explicit line_end values use them for range overlap."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
                line_end=15,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=14,
                line_end=20,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        # Should group because ranges overlap (10-15 and 14-20)
        assert len(result["groups"]) == 1
        assert len(result["groups"][0]) == 2

    def test_findings_without_line_end_treated_as_single_line(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Finding without line_end is treated as single-line range."""
        findings = [
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.stored",
                line_number=10,
                line_end=None,
            ),
            _make_test_finding(
                file="src/app.py",
                rule_id="xss.reflected",
                line_number=10,
                line_end=None,
            ),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.get_duplicate_candidates(run_id)

        # Both on same line -> should group
        assert len(result["groups"]) == 1
        assert len(result["groups"][0]) == 2


class TestResolveDuplicates:
    def test_happy_path_marks_loser_as_duplicate(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Calling resolve_duplicates marks loser with survivor_id."""
        findings = [
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=10),
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=11),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))
        inserted = finding_repo.get_findings_by_run_id(run_id)
        survivor_id = inserted[0].id
        loser_id = inserted[1].id

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.resolve_duplicates(run_id, survivor_id, [loser_id])

        assert result == {"status": "resolved", "count": 1}
        loser = finding_repo.get_finding(loser_id)
        assert loser is not None
        assert loser.duplicate_of == survivor_id

    def test_resolved_duplicate_filtered_from_reportable(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """After resolve_duplicates, loser filtered from reportable findings."""
        findings = [
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=10),
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=11),
        ]
        finding_repo.insert_findings(
            run_id, normalize_test_findings(findings), should_report=True
        )
        inserted = finding_repo.get_findings_by_run_id(run_id)
        survivor_id = inserted[0].id
        loser_id = inserted[1].id

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        service.resolve_duplicates(run_id, survivor_id, [loser_id])

        reportable = finding_repo.get_reportable_findings()
        reportable_ids = [f.id for f in reportable]
        assert survivor_id in reportable_ids
        assert loser_id not in reportable_ids

    def test_survivor_not_found(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Calling resolve_duplicates with non-existent survivor returns error."""
        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.resolve_duplicates(run_id, 9999, [])

        assert result == {"status": "rejected", "error": "survivor not found"}

    def test_survivor_already_duplicate(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Survivor marked as duplicate of another cannot be a survivor."""
        findings = [
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=10),
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=11),
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=12),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))
        inserted = finding_repo.get_findings_by_run_id(run_id)
        a_id = inserted[0].id
        b_id = inserted[1].id
        c_id = inserted[2].id

        finding_repo.mark_as_duplicate(b_id, a_id)

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.resolve_duplicates(run_id, b_id, [c_id])

        assert result == {
            "status": "rejected",
            "error": "survivor is already marked as a duplicate",
        }
        c = finding_repo.get_finding(c_id)
        assert c is not None
        assert c.duplicate_of is None

    def test_empty_removed_ids(
        self,
        run_id: int,
        finding_repo: FindingRepository,
        run_repo: RunRepository,
    ) -> None:
        """Calling with empty removed_ids returns count=0."""
        findings = [
            _make_test_finding(file="src/app.py", rule_id="xss.stored", line_number=10),
        ]
        finding_repo.insert_findings(run_id, normalize_test_findings(findings))
        inserted = finding_repo.get_findings_by_run_id(run_id)
        survivor_id = inserted[0].id

        service = McpIngestService(finding_repo=finding_repo, run_repo=run_repo)
        result = service.resolve_duplicates(run_id, survivor_id, [])

        assert result == {"status": "resolved", "count": 0}
