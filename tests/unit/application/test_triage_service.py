"""Unit tests for ``application.triage.triage_service.TriageService``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.triage.factory import TriageProviderNotConfiguredError
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

    def test_for_project_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            TriageService.for_project(registry, 7)  # type: ignore[arg-type]

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
            TriageService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_start_triage_validates_provider_before_repo_access(
        self,
    ) -> None:
        run_repo = MagicMock()
        triage_repo = MagicMock()
        service = TriageService(run_repo=run_repo, triage_repo=triage_repo)

        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured",
            side_effect=TriageProviderNotConfiguredError("Triage is disabled."),
        ):
            with pytest.raises(TriageProviderNotConfiguredError, match="disabled"):
                service.start_triage(
                    base_path="/tmp/base",
                    project_id=1,
                    project_name="proj",
                    tool_registry=MagicMock(),
                )

        run_repo.latest_run_id.assert_not_called()

    def test_resume_triage_validates_provider_before_repo_access(
        self,
    ) -> None:
        run_repo = MagicMock()
        triage_repo = MagicMock()
        service = TriageService(run_repo=run_repo, triage_repo=triage_repo)

        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured",
            side_effect=TriageProviderNotConfiguredError("Triage is disabled."),
        ):
            with pytest.raises(TriageProviderNotConfiguredError, match="disabled"):
                service.resume_triage(
                    base_path="/tmp/base",
                    project_id=1,
                    project_name="proj",
                    scan_run_id=9,
                    tool_registry=MagicMock(),
                )

        triage_repo.summarize_for_run.assert_not_called()
