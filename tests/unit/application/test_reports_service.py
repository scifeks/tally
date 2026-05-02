"""Unit tests for ``application.reporting.reports_service.ReportsService``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from application.reporting.reports_service import ProjectNotFound, ReportsService
from domain.projects.entry import ProjectRow


class _StubReportRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "ReportsService unit tests should not invoke ReportRepositoryPort"
        )


class _StubDraftRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "ReportsService unit tests should not invoke DraftRepositoryPort"
        )


class TestReportsService:
    def test_report_repo_property_exposes_constructed_handle(self) -> None:
        report_repo = _StubReportRepo()
        draft_repo = _StubDraftRepo()
        service = ReportsService(
            report_repo=report_repo,  # type: ignore[arg-type]
            draft_repo=draft_repo,  # type: ignore[arg-type]
        )
        assert service.report_repo is report_repo

    def test_draft_repo_property_exposes_constructed_handle(self) -> None:
        report_repo = _StubReportRepo()
        draft_repo = _StubDraftRepo()
        service = ReportsService(
            report_repo=report_repo,  # type: ignore[arg-type]
            draft_repo=draft_repo,  # type: ignore[arg-type]
        )
        assert service.draft_repo is draft_repo

    def test_for_project_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            ReportsService.for_project(registry, 7)  # type: ignore[arg-type]

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
            ReportsService.for_project(registry, 7)  # type: ignore[arg-type]
