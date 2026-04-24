"""Integration tests: sort_by / sort_dir support for findings queries."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.findings.sort import FindingSortColumn, InvalidSortColumn, SortDirection
from infrastructure.store import make_store

pytestmark = pytest.mark.integration

_PROJECT = "sort-test"


def _repos(tmp_path: Path):  # type: ignore[return]
    run_repo, finding_repo, _, _ = make_store(tmp_path, _PROJECT)
    return run_repo, finding_repo


# One finding per severity tier; insertion order: low, medium, critical, high, info.
_SEVERITY_FIXTURES = [
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "low",
        "confidence": "confirmed",
        "profile": "repo1",
        "file_path": "low.py",
        "rule_id": "rule-low",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "medium",
        "confidence": "confirmed",
        "profile": "repo1",
        "file_path": "medium.py",
        "rule_id": "rule-medium",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "critical",
        "confidence": "confirmed",
        "profile": "repo1",
        "file_path": "critical.py",
        "rule_id": "rule-critical",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "high",
        "confidence": "confirmed",
        "profile": "repo1",
        "file_path": "high.py",
        "rule_id": "rule-high",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "informational",
        "confidence": "confirmed",
        "profile": "repo1",
        "file_path": "info.py",
        "rule_id": "rule-info",
    },
]


class TestSortBySeverity:
    def test_asc_returns_critical_first(self, tmp_path: Path) -> None:
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.insert_findings(run_id, _SEVERITY_FIXTURES)

        results = finding_repo.search(
            {
                "conditions": [],
                "sort_by": FindingSortColumn.SEVERITY,
                "sort_dir": SortDirection.ASC,
                "page": 1,
                "page_size": 200,
            }
        )

        severities = [r["metadata"]["severity"] for r in results]
        assert severities == ["critical", "high", "medium", "low", "informational"]

    def test_desc_returns_informational_first(self, tmp_path: Path) -> None:
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.insert_findings(run_id, _SEVERITY_FIXTURES)

        results = finding_repo.search(
            {
                "conditions": [],
                "sort_by": FindingSortColumn.SEVERITY,
                "sort_dir": SortDirection.DESC,
                "page": 1,
                "page_size": 200,
            }
        )

        severities = [r["metadata"]["severity"] for r in results]
        assert severities == ["informational", "low", "medium", "high", "critical"]

    def test_asc_is_semantic_not_alphabetical(self, tmp_path: Path) -> None:
        """Semantic ASC: critical(0) < high(1) < medium(2) < low(3) < info(4).

        Alphabetical ASC would give: critical < high < informational < low < medium.
        Asserting low before informational proves integer ranks are used, not strings.
        """
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.insert_findings(run_id, _SEVERITY_FIXTURES)

        results = finding_repo.search(
            {
                "conditions": [],
                "sort_by": FindingSortColumn.SEVERITY,
                "sort_dir": SortDirection.ASC,
                "page": 1,
                "page_size": 200,
            }
        )

        severities = [r["metadata"]["severity"] for r in results]
        low_idx = severities.index("low")
        info_idx = severities.index("informational")
        assert low_idx < info_idx, (
            f"semantic sort puts 'low' (rank 3) before 'informational' (rank 4);"
            f" got {severities}"
        )


class TestSortByTool:
    def test_asc_alphabetical(self, tmp_path: Path) -> None:
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        multi_tool = [
            {
                "tool": "zap",
                "domain": "network",
                "finding_type": "vulnerability",
                "severity": "medium",
                "confidence": "confirmed",
                "profile": "repo1",
            },
            {
                "tool": "gitleaks",
                "domain": "code",
                "finding_type": "secret",
                "severity": "high",
                "confidence": "confirmed",
                "profile": "repo1",
            },
            {
                "tool": "semgrep",
                "domain": "code",
                "finding_type": "vulnerability",
                "severity": "low",
                "confidence": "confirmed",
                "profile": "repo1",
            },
        ]
        finding_repo.insert_findings(run_id, multi_tool)

        results = finding_repo.search(
            {
                "conditions": [],
                "sort_by": FindingSortColumn.TOOL,
                "sort_dir": SortDirection.ASC,
                "page": 1,
                "page_size": 200,
            }
        )

        tools = [r["metadata"]["tool"] for r in results]
        assert tools == sorted(tools)


class TestSortByTitle:
    def test_json_extract_sort_asc(self, tmp_path: Path) -> None:
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        titled = [
            {
                "tool": "semgrep",
                "domain": "code",
                "finding_type": "vulnerability",
                "severity": "low",
                "confidence": "confirmed",
                "profile": "repo1",
                "file_path": "z.py",
                "rule_id": "rule-z",
                "title": "Zebra Issue",
            },
            {
                "tool": "semgrep",
                "domain": "code",
                "finding_type": "vulnerability",
                "severity": "low",
                "confidence": "confirmed",
                "profile": "repo1",
                "file_path": "a.py",
                "rule_id": "rule-a",
                "title": "Alpha Issue",
            },
            {
                "tool": "semgrep",
                "domain": "code",
                "finding_type": "vulnerability",
                "severity": "low",
                "confidence": "confirmed",
                "profile": "repo1",
                "file_path": "m.py",
                "rule_id": "rule-m",
                "title": "Mango Issue",
            },
        ]
        finding_repo.insert_findings(run_id, titled)

        results = finding_repo.search(
            {
                "conditions": [],
                "sort_by": FindingSortColumn.TITLE,
                "sort_dir": SortDirection.ASC,
                "page": 1,
                "page_size": 200,
            }
        )

        titles = [r["metadata"].get("title") for r in results]
        non_null = [t for t in titles if t]
        assert non_null == sorted(non_null)


class TestDefaultSort:
    def test_returns_all_findings(self, tmp_path: Path) -> None:
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        finding_repo.insert_findings(run_id, _SEVERITY_FIXTURES)

        results = finding_repo.search({"conditions": [], "page": 1, "page_size": 200})

        assert len(results) == len(_SEVERITY_FIXTURES)

    def test_default_direction_is_desc_by_id_when_first_seen_tied(
        self, tmp_path: Path
    ) -> None:
        """When all findings share the same first_seen, tie-break on id DESC."""
        run_repo, finding_repo = _repos(tmp_path)
        run_id = run_repo.create_run({})
        three = _SEVERITY_FIXTURES[:3]  # low, medium, critical → ids 1, 2, 3
        finding_repo.insert_findings(run_id, three)

        results = finding_repo.search({"conditions": [], "page": 1, "page_size": 200})

        # id DESC → last-inserted (index 2 = critical) appears first
        first_rule_id = results[0]["metadata"]["rule_id"]
        assert first_rule_id == three[-1]["rule_id"]


class TestSortColumnValidation:
    def test_from_label_bogus_raises_invalid_sort_column(self) -> None:
        with pytest.raises(InvalidSortColumn):
            FindingSortColumn.from_label("bogus_column")

    def test_invalid_sort_column_is_value_error(self) -> None:
        with pytest.raises(ValueError):
            FindingSortColumn.from_label("not_a_real_column")
