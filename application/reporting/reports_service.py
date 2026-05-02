"""Application service for the reports + drafts persistence surface.

Owns per-request construction of the report and draft repos so route
modules do not import infrastructure persistence directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.drafts import DraftRepository
from infrastructure.store.repositories.reports import ReportRepository

if TYPE_CHECKING:
    from fastapi import Request

    from application.ports.draft_repository import DraftRepositoryPort
    from application.ports.report_repository import ReportRepositoryPort


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class ReportsService:
    """Reports + drafts facade bound to a single project."""

    def __init__(
        self,
        report_repo: ReportRepositoryPort,
        draft_repo: DraftRepositoryPort,
    ) -> None:
        self._report_repo = report_repo
        self._draft_repo = draft_repo

    @classmethod
    def from_request(cls, request: Request, project_id: int) -> Self:
        registry = request.app.state.project_registry
        row = registry.resolve_by_id(project_id)
        if row is None or row.get("archived_at"):
            raise ProjectNotFound(f"project {project_id} not found")
        paths = ProjectPaths.from_registry_row(row)
        paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()
        return cls(
            report_repo=ReportRepository(factory),
            draft_repo=DraftRepository(factory),
        )

    @property
    def report_repo(self) -> ReportRepositoryPort:
        return self._report_repo

    @property
    def draft_repo(self) -> DraftRepositoryPort:
        return self._draft_repo
