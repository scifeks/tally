"""Application service for the triage_batches persistence surface.

Owns per-request construction of the triage batch and run repos so
route modules do not import infrastructure persistence directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.triage import TriageBatchRepository

if TYPE_CHECKING:
    from fastapi import Request

    from application.ports.run_repository import RunRepositoryPort
    from application.ports.triage_batch_repository import TriageBatchRepositoryPort


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class TriageService:
    """Triage_batches facade bound to a single project."""

    def __init__(
        self,
        run_repo: RunRepositoryPort,
        triage_repo: TriageBatchRepositoryPort,
    ) -> None:
        self._run_repo = run_repo
        self._triage_repo = triage_repo

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
            run_repo=RunRepository(factory),
            triage_repo=TriageBatchRepository(factory),
        )

    @property
    def run_repo(self) -> RunRepositoryPort:
        return self._run_repo

    @property
    def triage_repo(self) -> TriageBatchRepositoryPort:
        return self._triage_repo
