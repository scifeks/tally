"""Unit tests for FindingRepository.count_aggregates and distinct_facet_values."""

from __future__ import annotations

from pathlib import Path

import pytest

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
def repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


def _insert(factory: ConnectionFactory, findings: list[dict]) -> None:

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    repo_ids: dict[str, int] = {}
    patched: list[dict] = []
    for f in findings:
        repo_name = f.get("repo")
        if repo_name and repo_name not in repo_ids:
            with factory.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO repositories (name) VALUES (?)",
                    (repo_name,),
                )
                repo_ids[repo_name] = cur.lastrowid  # type: ignore[assignment]
        if repo_name:
            patched.append({**f, "repo_id": repo_ids[repo_name]})
        else:
            patched.append(f)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings(patched))


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


class TestFilterOptionsEmpty:
    def test_empty_db_returns_empty_dimensions(self, repo: FindingRepository) -> None:
        result = repo.filter_options({"conditions": []})
        for key in (
            "severity",
            "status",
            "confidence",
            "domain",
            "segment",
            "tool",
            "finding_type",
            "repo",
        ):
            assert result[key] == [], f"expected empty list for {key!r}"


class TestFilterOptionsNoFilters:
    def test_all_dimensions_populated(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "severity": "high",
                    "segment": "sast",
                    "status": "active",
                    "confidence": "confirmed",
                    "url": "u1",
                    "repo": "alpha",
                    "finding_type": ["vulnerability"],
                },
                {
                    "tool": "bandit",
                    "domain": "code",
                    "severity": "medium",
                    "segment": "sast",
                    "status": "active",
                    "confidence": "probable",
                    "url": "u2",
                    "repo": "beta",
                    "finding_type": ["weakness"],
                },
            ],
        )
        result = repo.filter_options({"conditions": []})

        sev_values = {item["value"] for item in result["severity"]}
        assert sev_values == {"high", "medium"}
        sev_counts = {item["value"]: item["count"] for item in result["severity"]}
        assert sev_counts == {"high": 1, "medium": 1}

        tool_values = {item["value"] for item in result["tool"]}
        assert tool_values == {"semgrep", "bandit"}

        ft_values = {item["value"] for item in result["finding_type"]}
        assert ft_values == {"vulnerability", "weakness"}

        repo_labels = {item["label"] for item in result["repo"]}
        assert repo_labels == {"alpha", "beta"}
        for entry in result["repo"]:
            assert isinstance(entry["value"], int)
            assert entry["count"] == 1


class TestFilterOptionsStrictSemantics:
    def test_severity_filter_applies_to_every_dimension(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "severity": "high",
                    "segment": "sast",
                    "status": "active",
                    "url": "u1",
                    "repo": "alpha",
                },
                {
                    "tool": "bandit",
                    "domain": "code",
                    "severity": "low",
                    "segment": "sast",
                    "status": "fixed",
                    "url": "u2",
                    "repo": "beta",
                },
            ],
        )
        filters = {
            "conditions": [("severity", "=", ["high"])],
        }
        result = repo.filter_options(filters)

        # severity dim: only "high" survives the strict filter.
        assert [item["value"] for item in result["severity"]] == ["high"]
        # tool dim: only "semgrep" (the tool used by the high-severity row).
        assert [item["value"] for item in result["tool"]] == ["semgrep"]
        # status dim: only "active".
        assert [item["value"] for item in result["status"]] == ["active"]
        # repo dim: only "alpha".
        assert [item["label"] for item in result["repo"]] == ["alpha"]

    def test_combined_filters_intersect(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "severity": "high",
                    "confidence": "confirmed",
                    "segment": "sast",
                    "url": "u1",
                },
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "severity": "high",
                    "confidence": "probable",
                    "segment": "sast",
                    "url": "u2",
                },
            ],
        )
        filters = {
            "conditions": [
                ("severity", "=", ["high"]),
                ("confidence", "=", ["confirmed"]),
            ],
        }
        result = repo.filter_options(filters)
        # Only the confirmed+high finding survives.
        assert [item["value"] for item in result["severity"]] == ["high"]
        sev_counts = {item["value"]: item["count"] for item in result["severity"]}
        assert sev_counts == {"high": 1}
        assert [item["value"] for item in result["confidence"]] == ["confirmed"]


class TestFilterOptionsZeroCountsOmitted:
    def test_no_match_returns_empty_arrays(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [{"tool": "t", "domain": "code", "severity": "high", "url": "u"}],
        )
        # Filter for a severity that does not exist → every dim empty.
        result = repo.filter_options({"conditions": [("severity", "=", ["critical"])]})
        for key in (
            "severity",
            "status",
            "confidence",
            "domain",
            "segment",
            "tool",
            "finding_type",
            "repo",
        ):
            assert result[key] == [], f"expected empty list for {key!r}"

    def test_low_severity_dropped_when_none_present(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {"tool": "t", "domain": "code", "severity": "high", "url": "u1"},
                {"tool": "t", "domain": "code", "severity": "medium", "url": "u2"},
            ],
        )
        result = repo.filter_options({"conditions": []})
        sev_values = {item["value"] for item in result["severity"]}
        # Only high and medium are present; low/critical/informational dropped.
        assert sev_values == {"high", "medium"}


class TestFilterOptionsFindingTypeJsonEach:
    def test_finding_type_unrolled_per_array_element(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "t",
                    "domain": "code",
                    "severity": "high",
                    "url": "u1",
                    "finding_type": ["vulnerability", "weakness"],
                },
                {
                    "tool": "t",
                    "domain": "code",
                    "severity": "high",
                    "url": "u2",
                    "finding_type": ["weakness"],
                },
            ],
        )
        result = repo.filter_options({"conditions": []})
        ft_counts = {item["value"]: item["count"] for item in result["finding_type"]}
        # vulnerability appears in 1 finding; weakness in 2.
        assert ft_counts == {"vulnerability": 1, "weakness": 2}


class TestFilterOptionsRepoLabel:
    def test_repo_dim_returns_id_label_count(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {
                    "tool": "t",
                    "domain": "code",
                    "severity": "high",
                    "url": "u1",
                    "repo": "myrepo",
                },
                {
                    "tool": "t",
                    "domain": "code",
                    "severity": "high",
                    "url": "u2",
                    "repo": "myrepo",
                },
            ],
        )
        result = repo.filter_options({"conditions": []})
        assert len(result["repo"]) == 1
        entry = result["repo"][0]
        assert isinstance(entry["value"], int)
        assert entry["label"] == "myrepo"
        assert entry["count"] == 2


class TestGetFindingsMarkedForReport:
    def test_returns_should_report_rows_regardless_of_triage(
        self, factory: ConnectionFactory, repo: FindingRepository
    ) -> None:
        _insert(
            factory,
            [
                {"tool": "t", "domain": "code", "severity": "high", "url": "u1"},
                {"tool": "t", "domain": "code", "severity": "high", "url": "u2"},
                {"tool": "t", "domain": "code", "severity": "high", "url": "u3"},
            ],
        )
        with factory.connect() as conn:
            ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM findings ORDER BY id"
                ).fetchall()
            ]
            untriaged_marked, triaged_marked, triaged_excluded = ids
            conn.execute(
                "UPDATE findings SET should_report = 1 WHERE id = ?",
                (untriaged_marked,),
            )
            conn.execute(
                "UPDATE findings SET should_report = 1, "
                "triaged_by = 'analyst', triaged_at = '2026-01-01T00:00:00Z' "
                "WHERE id = ?",
                (triaged_marked,),
            )
            conn.execute(
                "UPDATE findings SET should_report = 0, "
                "triaged_by = 'analyst', triaged_at = '2026-01-01T00:00:00Z' "
                "WHERE id = ?",
                (triaged_excluded,),
            )

        result_ids = {f.id for f in repo.get_findings_marked_for_report()}
        assert result_ids == {untriaged_marked, triaged_marked}
