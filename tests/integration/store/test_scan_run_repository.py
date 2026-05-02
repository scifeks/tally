"""Tests for the Phase 5.1 RunRepository surface (scan_runs + run_tools)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from domain.scans.entry import ScanRunRow, ToolRunRow  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "tally.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


class TestCreateFull:
    def test_create_writes_json_arrays(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=7,
            repo_ids=["dvwa", "dvpwa"],
            tool_ids=["gitleaks", "semgrep"],
            domains=["code", "web"],
            skip_enrichment=True,
        )
        row = repo.get(run_id)
        assert row is not None
        assert row.project_id == 7
        assert row.repo_ids == ["dvwa", "dvpwa"]
        assert row.tool_ids == ["gitleaks", "semgrep"]
        assert row.domains == ["code", "web"]
        assert row.skip_enrichment is True
        assert row.status == "queued"

    def test_create_default_status_is_queued(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )
        row = repo.get(run_id)
        assert row is not None
        assert row.status == "queued"
        assert row.findings_count is None


class TestStatusTransitions:
    def test_set_status_persists(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )
        repo.set_status(run_id, "running")
        assert repo.get(run_id).status == "running"  # type: ignore[union-attr]
        repo.set_status(run_id, "done")
        assert repo.get(run_id).status == "done"  # type: ignore[union-attr]

    def test_set_status_rejects_unknown(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )
        with pytest.raises(ValueError):
            repo.set_status(run_id, "bogus")

    def test_started_finished_findings_persist(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )
        repo.set_started_at(run_id, "2026-04-25T10:00:00+00:00")
        repo.set_finished_at(run_id, "2026-04-25T10:30:00+00:00")
        repo.set_findings_count(run_id, 42)
        row = repo.get(run_id)
        assert row is not None
        assert row.started_at == "2026-04-25T10:00:00+00:00"
        assert row.finished_at == "2026-04-25T10:30:00+00:00"
        assert row.findings_count == 42


class TestListForProject:
    def _make_runs(self, repo: RunRepository) -> list[int]:
        ids = []
        for project_id, status in [
            (1, "done"),
            (1, "done"),
            (1, "failed"),
            (2, "done"),
        ]:
            run_id = repo.create(
                project_id=project_id,
                repo_ids=[],
                tool_ids=[],
                domains=[],
                skip_enrichment=False,
            )
            repo.set_status(run_id, status)
            ids.append(run_id)
        return ids

    def test_filters_by_project_id(self, repo: RunRepository) -> None:
        self._make_runs(repo)
        rows, total = repo.list_for_project(1)
        assert total == 3
        assert {r.project_id for r in rows} == {1}

    def test_filters_by_status(self, repo: RunRepository) -> None:
        self._make_runs(repo)
        rows, total = repo.list_for_project(1, status="done")
        assert total == 2
        assert {r.status for r in rows} == {"done"}

    def test_pagination(self, repo: RunRepository) -> None:
        self._make_runs(repo)
        page1, total = repo.list_for_project(1, limit=2, offset=0)
        page2, _ = repo.list_for_project(1, limit=2, offset=2)
        assert total == 3
        assert len(page1) == 2
        assert len(page2) == 1
        # newest-first
        assert page1[0].id > page1[1].id

    def test_unknown_project_returns_empty(self, repo: RunRepository) -> None:
        self._make_runs(repo)
        rows, total = repo.list_for_project(999)
        assert rows == []
        assert total == 0


class TestToolRunCRUD:
    def test_add_and_get_with_tool_runs(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=["dvwa"],
            tool_ids=["gitleaks"],
            domains=["code"],
            skip_enrichment=False,
        )
        tr_id = repo.add_tool_run(
            run_id=run_id,
            tool="gitleaks",
            repo="dvwa",
            domain="code",
        )
        result = repo.get_with_tool_runs(run_id)
        assert result is not None
        scan, tool_runs = result
        assert isinstance(scan, ScanRunRow)
        assert len(tool_runs) == 1
        assert isinstance(tool_runs[0], ToolRunRow)
        assert tool_runs[0].id == tr_id
        assert tool_runs[0].tool == "gitleaks"
        assert tool_runs[0].repo == "dvwa"
        assert tool_runs[0].status == "queued"

    def test_update_tool_run_partial(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )
        tr_id = repo.add_tool_run(run_id=run_id, tool="gitleaks")
        repo.update_tool_run(
            tr_id,
            status="done",
            started_at="2026-04-25T10:00:00+00:00",
            finished_at="2026-04-25T10:00:30+00:00",
            exit_code=0,
            findings_count=5,
        )
        result = repo.get_with_tool_runs(run_id)
        assert result is not None
        _, tool_runs = result
        tr = tool_runs[0]
        assert tr.status == "done"
        assert tr.exit_code == 0
        assert tr.findings_count == 5

    def test_update_tool_run_no_fields_is_noop(self, repo: RunRepository) -> None:
        run_id = repo.create(
            project_id=1,
            repo_ids=[],
            tool_ids=[],
            domains=[],
            skip_enrichment=False,
        )
        tr_id = repo.add_tool_run(run_id=run_id, tool="gitleaks")
        repo.update_tool_run(tr_id)
        result = repo.get_with_tool_runs(run_id)
        assert result is not None


class TestLegacyShim:
    def test_create_run_still_works(self, repo: RunRepository) -> None:
        """REPL parity: legacy create_run keeps inserting into scan_runs."""
        run_id = repo.create_run({"args": ["scan", "--repo", "dvwa"]})
        row = repo.get(run_id)
        assert row is not None
        assert row.args == {"args": ["scan", "--repo", "dvwa"]}
        assert row.project_id is None
        assert row.status is None
        assert row.repo_ids == []
