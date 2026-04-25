"""Unit tests for FindingRepository.count_aggregates and distinct_facet_values."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


def _insert(factory: ConnectionFactory, findings: list[dict]) -> None:
    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, findings)


class TestCountAggregatesEmpty:
    def test_empty_db_returns_empty_buckets(self, repo: FindingRepository) -> None:
        result = repo.count_aggregates()
        assert result["by_severity"] == {}
        assert result["by_domain"] == {}
        assert result["by_segment"] == {}
        assert result["by_repo"] == {}
        assert result["by_status"] == {}


class TestCountAggregatesSingleRow:
    def test_single_finding_appears_in_all_buckets(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "severity": "high",
                    "url": "http://example.com",
                    "segment": "sast",
                    "repo": "my-repo",
                    "status": "open",
                }
            ],
        )
        result = repo.count_aggregates()
        assert result["by_severity"].get("high") == 1
        assert result["by_domain"].get("code") == 1
        assert result["by_segment"].get("sast") == 1
        assert result["by_repo"].get("my-repo") == 1

    def test_severity_rank_translates_to_label(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [{"tool": "t", "domain": "code", "severity": "critical", "url": "u"}],
        )
        result = repo.count_aggregates()
        assert "critical" in result["by_severity"]
        assert result["by_severity"]["critical"] == 1

    def test_integer_keys_not_present_in_by_severity(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [{"tool": "t", "domain": "code", "severity": "low", "url": "u"}],
        )
        result = repo.count_aggregates()
        for key in result["by_severity"]:
            assert isinstance(key, str), f"expected str key, got {type(key)}: {key!r}"


class TestCountAggregatesMultiRow:
    def test_multiple_severities_bucketed_correctly(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {"tool": "t", "domain": "code", "severity": "high", "url": "u1"},
                {"tool": "t", "domain": "code", "severity": "high", "url": "u2"},
                {"tool": "t", "domain": "code", "severity": "low", "url": "u3"},
            ],
        )
        result = repo.count_aggregates()
        assert result["by_severity"]["high"] == 2
        assert result["by_severity"]["low"] == 1

    def test_multiple_domains_bucketed_correctly(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {"tool": "t", "domain": "code", "severity": "high", "url": "u1"},
                {"tool": "t", "domain": "web", "severity": "low", "url": "u2"},
                {"tool": "t", "domain": "web", "severity": "low", "url": "u3"},
            ],
        )
        result = repo.count_aggregates()
        assert result["by_domain"]["code"] == 1
        assert result["by_domain"]["web"] == 2

    def test_total_across_severity_equals_total_findings(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        rows = [
            {"tool": "t", "domain": "code", "severity": s, "url": f"u{i}"}
            for i, s in enumerate(["critical", "high", "medium", "low"])
        ]
        _insert(factory, rows)
        result = repo.count_aggregates()
        assert sum(result["by_severity"].values()) == 4


class TestDistinctFacetValuesEmpty:
    def test_empty_db_returns_empty_lists(self, repo: FindingRepository) -> None:
        result = repo.distinct_facet_values()
        for key in (
            "domains",
            "severities",
            "statuses",
            "confidence_levels",
            "finding_types",
            "tools",
            "repos",
            "segments",
        ):
            assert result[key] == [], f"expected empty list for {key!r}"


class TestDistinctFacetValuesSingleRow:
    def test_tool_appears_in_tools(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [{"tool": "dalfox", "domain": "web", "severity": "high", "url": "u"}],
        )
        assert "dalfox" in repo.distinct_facet_values()["tools"]

    def test_severity_label_in_severities(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [{"tool": "t", "domain": "code", "severity": "medium", "url": "u"}],
        )
        result = repo.distinct_facet_values()
        assert "medium" in result["severities"]
        for sev in result["severities"]:
            assert isinstance(sev, str)

    def test_finding_type_via_json_each(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "t",
                    "domain": "code",
                    "severity": "high",
                    "url": "u",
                    "finding_type": ["vulnerability", "weakness"],
                }
            ],
        )
        result = repo.distinct_facet_values()
        assert "vulnerability" in result["finding_types"]
        assert "weakness" in result["finding_types"]


class TestDistinctFacetValuesMultiRow:
    def test_deduplication(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {"tool": "semgrep", "domain": "code", "severity": "high", "url": "u1"},
                {"tool": "semgrep", "domain": "code", "severity": "high", "url": "u2"},
            ],
        )
        result = repo.distinct_facet_values()
        assert result["tools"].count("semgrep") == 1
        assert result["domains"].count("code") == 1

    def test_results_are_sorted(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {"tool": "zap", "domain": "web", "severity": "low", "url": "u1"},
                {"tool": "dalfox", "domain": "code", "severity": "high", "url": "u2"},
            ],
        )
        result = repo.distinct_facet_values()
        assert result["tools"] == sorted(result["tools"])
        assert result["domains"] == sorted(result["domains"])
