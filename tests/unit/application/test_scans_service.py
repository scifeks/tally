"""Unit tests for ``application.scans.scans_service.ScansService``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from application.scans.scans_service import ProjectNotFound, ScansService
from domain.projects.entry import ProjectRow


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
        service = ScansService(run_repo=repo)  # type: ignore[arg-type]
        assert service.run_repo is repo

    def test_from_request_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(project_registry=registry))
        )
        with pytest.raises(ProjectNotFound):
            ScansService.from_request(request, 7)  # type: ignore[arg-type]

    def test_from_request_raises_when_project_archived(self) -> None:
        archived = ProjectRow(
            id=7,
            name="p",
            path="/tmp/p",
            created_at="2026-05-01T00:00:00Z",
            archived_at="2026-05-01T00:00:00Z",
        )
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: archived)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(project_registry=registry))
        )
        with pytest.raises(ProjectNotFound):
            ScansService.from_request(request, 7)  # type: ignore[arg-type]

    def test_mark_stale_failed_for_all_projects_handles_empty_registry(self) -> None:
        registry = _StubProjectRegistry(projects=[])
        ScansService.mark_stale_failed_for_all_projects(registry)  # type: ignore[arg-type]
