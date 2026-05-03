"""Unit tests for ``application.scans.scans_service.ScansService``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.locking.cancellation import CancellationToken
from application.scans.scans_service import (
    ProjectNotFound,
    ScanNotCancellable,
    ScanNotFound,
    ScansService,
)
from application.tools.scan_run_registry import ScanRunRegistry
from domain.projects.entry import ProjectRow
from domain.scans.entry import ScanRunRow


class _StubRunRepo:
    """Minimal Protocol satisfaction; no method is exercised in these tests."""

    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "ScansService unit tests should not invoke RunRepositoryPort"
        )


class _StubProjectRegistry:
    def __init__(self, projects: list[ProjectRow] | None = None) -> None:
        self._projects = projects or []

    def list_active(self) -> list[ProjectRow]:
        return list(self._projects)


class TestScansService:
    def test_run_repo_property_exposes_constructed_handle(self) -> None:
        repo = _StubRunRepo()
        service = ScansService(run_repo=repo, project_id=1)  # type: ignore[arg-type]
        assert service.run_repo is repo

    def test_for_project_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            ScansService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_for_project_raises_when_project_archived(self) -> None:
        archived = ProjectRow(
            id=7,
            name="p",
            path="/tmp/p",
            created_at="2026-05-01T00:00:00Z",
            archived_at="2026-05-01T00:00:00Z",
        )
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: archived)
        with pytest.raises(ProjectNotFound):
            ScansService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_mark_stale_failed_for_all_projects_handles_empty_registry(self) -> None:
        registry = _StubProjectRegistry(projects=[])
        ScansService.mark_stale_failed_for_all_projects(registry)  # type: ignore[arg-type]


def _row(*, project_id: int | None = 1, status: str | None = "running") -> ScanRunRow:
    return ScanRunRow(
        id=99,
        project_id=project_id,
        args={},
        created_at="2026-05-02T00:00:00Z",
        status=status,
        started_at=None,
        finished_at=None,
        repo_ids=[],
        tool_ids=[],
        domains=[],
        skip_enrichment=False,
        findings_count=None,
    )


def _service(
    *, project_id: int = 1, run_repo: MagicMock | None = None
) -> tuple[ScansService, ScanRunRegistry, MagicMock]:
    registry = ScanRunRegistry()
    repo = run_repo or MagicMock()
    service = ScansService(
        run_repo=repo, project_id=project_id, scan_run_registry=registry
    )
    return service, registry, repo


class TestScansServiceCancelScan:
    def test_happy_path_signals_token_and_marks_cancelling(self) -> None:
        service, registry, repo = _service(project_id=5)
        token = CancellationToken()
        registry.register(run_id=99, project_id=5, cancel_token=token)

        service.cancel_scan(99)

        assert token.is_set() is True
        repo.set_status.assert_called_once_with(99, "cancelling")

    def test_unknown_run_id_raises_scan_not_found(self) -> None:
        service, _registry, repo = _service(project_id=5)
        repo.get.return_value = None

        with pytest.raises(ScanNotFound):
            service.cancel_scan(404)

        repo.set_status.assert_not_called()

    def test_cross_project_handle_raises_not_found_without_setting_token(self) -> None:
        service, registry, repo = _service(project_id=5)
        token = CancellationToken()
        registry.register(run_id=99, project_id=999, cancel_token=token)

        with pytest.raises(ScanNotFound):
            service.cancel_scan(99)

        assert token.is_set() is False
        repo.set_status.assert_not_called()

    def test_finished_run_raises_not_cancellable_with_status(self) -> None:
        service, _registry, repo = _service(project_id=5)
        repo.get.return_value = _row(project_id=5, status="done")

        with pytest.raises(ScanNotCancellable) as exc_info:
            service.cancel_scan(99)

        assert exc_info.value.status == "done"
        repo.set_status.assert_not_called()

    def test_row_in_other_project_raises_scan_not_found(self) -> None:
        service, _registry, repo = _service(project_id=5)
        repo.get.return_value = _row(project_id=999, status="running")

        with pytest.raises(ScanNotFound):
            service.cancel_scan(99)


class TestScansServiceCancelAll:
    def test_empty_registry_returns_empty_list_and_writes_nothing(self) -> None:
        service, _registry, repo = _service(project_id=5)
        assert service.cancel_all() == []
        repo.set_status.assert_not_called()

    def test_only_handles_for_bound_project_are_cancelled(self) -> None:
        service, registry, repo = _service(project_id=5)
        t1, t2, t3 = CancellationToken(), CancellationToken(), CancellationToken()
        registry.register(run_id=1, project_id=5, cancel_token=t1)
        registry.register(run_id=2, project_id=5, cancel_token=t2)
        registry.register(run_id=3, project_id=999, cancel_token=t3)

        cancelled = service.cancel_all()

        assert sorted(cancelled) == [1, 2]
        assert t1.is_set() and t2.is_set()
        assert t3.is_set() is False
        assert repo.set_status.call_count == 2
        repo.set_status.assert_any_call(1, "cancelling")
        repo.set_status.assert_any_call(2, "cancelling")

    def test_per_row_set_status_failure_is_swallowed(self) -> None:
        service, registry, repo = _service(project_id=5)
        t1 = CancellationToken()
        registry.register(run_id=1, project_id=5, cancel_token=t1)
        repo.set_status.side_effect = RuntimeError("db blew up")

        cancelled = service.cancel_all()

        assert cancelled == [1]
        assert t1.is_set() is True


class TestScansServicePeekActiveRun:
    def test_returns_handle_when_registered(self) -> None:
        service, registry, _repo = _service(project_id=5)
        token = CancellationToken()
        registry.register(run_id=99, project_id=5, cancel_token=token)
        handle = service.peek_active_run(99)
        assert handle is not None
        assert handle.run_id == 99
        assert handle.project_id == 5

    def test_returns_none_when_unregistered(self) -> None:
        service, _registry, _repo = _service(project_id=5)
        assert service.peek_active_run(99) is None


class TestScansServiceListActiveRuns:
    def test_returns_only_handles_for_bound_project(self) -> None:
        service, registry, _repo = _service(project_id=5)
        t1, t2 = CancellationToken(), CancellationToken()
        registry.register(run_id=1, project_id=5, cancel_token=t1)
        registry.register(run_id=2, project_id=999, cancel_token=t2)

        handles = service.list_active_runs()

        assert [h.run_id for h in handles] == [1]

    def test_returns_empty_list_when_no_handles(self) -> None:
        service, _registry, _repo = _service(project_id=5)
        assert service.list_active_runs() == []


class TestScansServiceRecordRunToolCounts:
    def test_translates_mapping_to_row_list_and_persists(self) -> None:
        service, _registry, repo = _service(project_id=5)

        service.record_run_tool_counts(42, {"semgrep": 7, "gitleaks": 3})

        repo.add_run_tools.assert_called_once()
        run_id, rows = repo.add_run_tools.call_args.args
        assert run_id == 42
        assert sorted(rows, key=lambda r: r["tool"]) == [
            {"tool": "gitleaks", "findings_count": 3},
            {"tool": "semgrep", "findings_count": 7},
        ]

    def test_empty_mapping_short_circuits_without_touching_repo(self) -> None:
        service, _registry, repo = _service(project_id=5)

        service.record_run_tool_counts(42, {})

        repo.add_run_tools.assert_not_called()
