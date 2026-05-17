"""Unit tests for FindingHistoryRepository read methods."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.finding_history import FindingHistoryRepository
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.finding_helpers import normalize_test_findings

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "url": "https://example.com/path",
    "file_path": "src/app.py",
    "rule_id": "rule-a",
    "description": "SQL injection",
    "segment": "sast",
    "repo": "test-repo",
}


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def finding_id(factory: ConnectionFactory) -> int:
    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings([_BASE_FINDING]))
    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    return int(row["id"])


def _seed_history(
    factory: ConnectionFactory,
    finding_id: int,
    *,
    count: int = 1,
) -> None:
    with factory.connect() as conn:
        for i in range(count):
            conn.execute(
                """
                INSERT INTO finding_history
                    (finding_id, timestamp, before_values, after_values, source)
                VALUES (?, datetime('now', ? || ' seconds'), ?, ?, ?)
                """,
                (
                    finding_id,
                    f"-{i}",
                    json.dumps({"severity": "high"}),
                    json.dumps({"severity": "critical"}),
                    "web_ui",
                ),
            )


@pytest.fixture()
def history_repo(factory: ConnectionFactory) -> FindingHistoryRepository:
    return FindingHistoryRepository(factory)


class TestFindingHistoryRepositoryEmpty:
    def test_list_returns_empty_for_new_finding(
        self,
        history_repo: FindingHistoryRepository,
        finding_id: int,
    ) -> None:
        rows = history_repo.list_for_finding(finding_id)
        assert rows == []

    def test_count_returns_zero_for_new_finding(
        self,
        history_repo: FindingHistoryRepository,
        finding_id: int,
    ) -> None:
        assert history_repo.count_for_finding(finding_id) == 0


class TestFindingHistoryRepositoryWithData:
    def test_list_returns_correct_count(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=3)
        rows = history_repo.list_for_finding(finding_id)
        assert len(rows) == 3

    def test_count_matches_inserted(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=5)
        assert history_repo.count_for_finding(finding_id) == 5

    def test_json_round_trip_before_after_values(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=1)
        rows = history_repo.list_for_finding(finding_id)
        assert rows[0].before_values == {"severity": "high"}
        assert rows[0].after_values == {"severity": "critical"}

    def test_pagination_offset_limit(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=4)
        page1 = history_repo.list_for_finding(finding_id, offset=0, limit=2)
        page2 = history_repo.list_for_finding(finding_id, offset=2, limit=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert {r.id for r in page1}.isdisjoint({r.id for r in page2})

    def test_cascade_delete_removes_history(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=2)
        assert history_repo.count_for_finding(finding_id) == 2
        with factory.connect() as conn:
            conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
        assert history_repo.count_for_finding(finding_id) == 0

    def test_source_field_preserved(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=1)
        rows = history_repo.list_for_finding(finding_id)
        assert rows[0].source == "web_ui"

    def test_inference_context_none_when_not_set(
        self,
        history_repo: FindingHistoryRepository,
        factory: ConnectionFactory,
        finding_id: int,
    ) -> None:
        _seed_history(factory, finding_id, count=1)
        rows = history_repo.list_for_finding(finding_id)
        assert rows[0].inference_context is None
