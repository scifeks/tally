"""Unit tests for ``application.triage.triage_service.TriageService``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from application.triage.triage_service import ProjectNotFound, TriageService
from domain.projects.entry import ProjectRow


class _StubRunRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "TriageService unit tests should not invoke RunRepositoryPort"
        )


class _StubTriageRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "TriageService unit tests should not invoke TriageBatchRepositoryPort"
        )


class TestTriageService:
    def test_run_repo_property_exposes_constructed_handle(self) -> None:
        run_repo = _StubRunRepo()
        triage_repo = _StubTriageRepo()
        service = TriageService(
            run_repo=run_repo,  # type: ignore[arg-type]
            triage_repo=triage_repo,  # type: ignore[arg-type]
        )
        assert service.run_repo is run_repo

    def test_triage_repo_property_exposes_constructed_handle(self) -> None:
        run_repo = _StubRunRepo()
        triage_repo = _StubTriageRepo()
        service = TriageService(
            run_repo=run_repo,  # type: ignore[arg-type]
            triage_repo=triage_repo,  # type: ignore[arg-type]
        )
        assert service.triage_repo is triage_repo

    def test_from_request_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(project_registry=registry))
        )
        with pytest.raises(ProjectNotFound):
            TriageService.from_request(request, 7)  # type: ignore[arg-type]

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
            TriageService.from_request(request, 7)  # type: ignore[arg-type]
