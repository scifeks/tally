"""Persistence factory functions for application service construction.

Centralizes all SQLite/repository construction so the application layer
never imports from ``infrastructure.store``. Driving adapters (REPL
commands, web routes, composition roots) call these factories.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.project_paths import ProjectPaths
from infrastructure.endpoints.converters.endpoint_file_converter import (
    EndpointFileConverter,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.audit import AuditRepository
from infrastructure.store.repositories.chat_messages import (
    ChatMessageRepository,
)
from infrastructure.store.repositories.chat_sessions import (
    ChatSessionRepository,
)
from infrastructure.store.repositories.drafts import DraftRepository
from infrastructure.store.repositories.finding_history import (
    FindingHistoryRepository,
)
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.reports import ReportRepository
from infrastructure.store.repositories.repositories import (
    RepositoryRepository,
)
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)
from infrastructure.store.repositories.tool_overrides import (
    ToolOverridesRepository,
)
from infrastructure.store.repositories.triage import (
    TriageBatchRepository,
)
from infrastructure.store.repositories.url_findings import (
    UrlFindingRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from application.chat.session_service import ChatSessionService
    from application.findings.findings_service import FindingsService
    from application.ports.audit_repository import AuditRepositoryPort
    from application.ports.chat_session_repository import (
        ChatSessionRepositoryPort,
    )
    from application.ports.finding_event_sink import FindingEventSink
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.ports.run_repository import RunRepositoryPort
    from application.ports.tool_arg_profiles import (
        ToolArgProfilesRepositoryPort,
    )
    from application.ports.tool_overrides import (
        ToolOverridesRepositoryPort,
    )
    from application.ports.triage_batch_repository import (
        TriageBatchRepositoryPort,
    )
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.rag.knowledge_base import FindingKnowledgeBase
    from application.reporting.reports_service import ReportsService
    from application.scans.scans_service import ScansService
    from application.triage.triage_service import TriageService
    from application.url_inventory.url_list_service import (
        UrlListService,
    )
    from core.config.schemas import Repository


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


# ------------------------------------------------------------------
# Low-level helpers
# ------------------------------------------------------------------


def _init_factory(db_path: Path) -> ConnectionFactory:
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    return factory


def _resolve_project(registry: ProjectRegistryService, project_id: int) -> tuple:
    row = registry.resolve_by_id(project_id)
    if row is None or row.archived_at:
        raise ProjectNotFound(f"project {project_id} not found")
    paths = ProjectPaths.from_registry_row(row)
    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
    return row, paths


# ------------------------------------------------------------------
# Utility factories
# ------------------------------------------------------------------


def build_default_registry(
    base_path: str | Path,
) -> ProjectRegistryService:
    """Build a ProjectRegistryService rooted at base_path/tally.db."""
    from application.project.registry_service import (
        ProjectRegistryService as PRS,
    )
    from infrastructure.store.project_registry import (
        ProjectRegistryRepository,
    )

    repo = ProjectRegistryRepository(Path(base_path) / "tally.db")
    repo.init_schema()
    svc = PRS(repo)
    svc.sync(str(base_path))
    return svc


def init_project_schema(db_path: Path) -> None:
    """Create the schema for a project database."""
    _init_factory(db_path)


def make_store(
    base_path: str | Path, project_name: str
) -> tuple[
    RunRepositoryPort,
    FindingRepositoryPort,
    TriageBatchRepositoryPort,
    AuditRepositoryPort,
]:
    """Create all four core repositories for a project."""
    paths = ProjectPaths.from_canonical(base_path, project_name)
    factory = _init_factory(paths.findings_db)
    return (
        RunRepository(factory),
        FindingRepository(factory),
        TriageBatchRepository(factory),
        AuditRepository(factory),
    )


def load_active_repos(base_path: str | Path, project_name: str) -> list[Repository]:
    """Return active repos for the project, or [] if absent."""
    paths = ProjectPaths.from_canonical(base_path, project_name)
    if not paths.findings_db.exists():
        return []
    factory = _init_factory(paths.findings_db)
    return RepositoryRepository(factory).list_active()


def create_repo_repo(
    db_path: Path,
) -> ProjectRepoRepositoryPort:
    """Create a RepositoryRepository for the given DB."""
    return RepositoryRepository(_init_factory(db_path))


def create_finding_repo(
    db_path: Path,
) -> FindingRepositoryPort:
    """Create a FindingRepository for the given DB."""
    return FindingRepository(_init_factory(db_path))


def create_url_finding_repo(
    db_path: Path,
) -> UrlFindingRepositoryPort:
    """Create a UrlFindingRepository for the given DB."""
    return UrlFindingRepository(_init_factory(db_path))


def create_overrides_repo(
    db_path: Path,
) -> ToolOverridesRepositoryPort:
    """Create a ToolOverridesRepository for the given DB."""
    return ToolOverridesRepository(_init_factory(db_path))


def create_arg_profiles_repo(
    db_path: Path,
) -> ToolArgProfilesRepositoryPort:
    """Create a ToolArgProfilesRepository for the given DB."""
    return ToolArgProfilesRepository(_init_factory(db_path))


def create_scan_repos(
    db_path: Path,
) -> tuple[
    RunRepositoryPort,
    ChatSessionRepositoryPort,
    ToolArgProfilesRepositoryPort,
    ToolOverridesRepositoryPort,
]:
    """Create the repos needed to start a scan."""
    factory = _init_factory(db_path)
    return (
        RunRepository(factory),
        ChatSessionRepository(factory),
        ToolArgProfilesRepository(factory),
        ToolOverridesRepository(factory),
    )


def build_repo_factory(
    registry: ProjectRegistryService,
) -> Callable[[int], ProjectRepoRepositoryPort]:
    """Return a callable that creates a RepositoryRepository
    for a given project_id. For ProjectRepositoriesService.
    """

    def _factory(project_id: int) -> ProjectRepoRepositoryPort:
        _, paths = _resolve_project(registry, project_id)
        return RepositoryRepository(_init_factory(paths.findings_db))

    return _factory


def build_schema_initializer() -> Callable[[Path], None]:
    """Return a callable that initializes a project DB schema."""
    return lambda db_path: init_project_schema(db_path)


def build_url_repo_factory() -> Callable[[Path], UrlFindingRepositoryPort]:
    """Return a callable that creates a UrlFindingRepository."""
    return lambda db_path: create_url_finding_repo(db_path)


# ------------------------------------------------------------------
# Service factories (replace for_project classmethods)
# ------------------------------------------------------------------


def create_findings_service(
    registry: ProjectRegistryService,
    project_id: int,
    *,
    knowledge_base_cache: (dict[str, FindingKnowledgeBase | None] | None) = None,
    base_path: str | None = None,
    event_sink: FindingEventSink | None = None,
) -> FindingsService:
    """Build a FindingsService for a project."""
    from application.findings.analyst_service import (
        FindingAnalystService,
    )
    from application.findings.findings_service import FindingsService
    from application.locking import LockQueryService

    row, paths = _resolve_project(registry, project_id)
    findings_db_exists = paths.findings_db.exists()
    factory = _init_factory(paths.findings_db)
    finding_repo = FindingRepository(factory)
    history_repo = FindingHistoryRepository(factory)
    project_repo = RepositoryRepository(factory)
    analyst = FindingAnalystService(finding_repo)
    return FindingsService(
        finding_repo=finding_repo,
        history_repo=history_repo,
        project_repo=project_repo,
        analyst=analyst,
        lock_query=LockQueryService(),
        project_id=project_id,
        project_name=row.name,
        findings_db_exists=findings_db_exists,
        purge_tables=factory.purge_non_preserved_tables,
        knowledge_base_cache=knowledge_base_cache,
        base_path=base_path or "",
        event_sink=event_sink,
    )


def create_chat_session_service(
    registry: ProjectRegistryService,
    project_id: int,
) -> ChatSessionService:
    """Build a ChatSessionService for a project."""
    from application.chat.session_service import ChatSessionService

    _, paths = _resolve_project(registry, project_id)
    factory = _init_factory(paths.findings_db)
    return ChatSessionService(
        session_repo=ChatSessionRepository(factory),
        message_repo=ChatMessageRepository(factory),
    )


def create_reports_service(
    registry: ProjectRegistryService,
    project_id: int,
) -> ReportsService:
    """Build a ReportsService for a project."""
    from application.reporting.reports_service import ReportsService

    _, paths = _resolve_project(registry, project_id)
    factory = _init_factory(paths.findings_db)
    return ReportsService(
        report_repo=ReportRepository(factory),
        draft_repo=DraftRepository(factory),
        finding_repo=FindingRepository(factory),
        repo_repo=RepositoryRepository(factory),
    )


def create_scans_service(
    registry: ProjectRegistryService,
    project_id: int,
) -> ScansService:
    """Build a ScansService for a project."""
    from application.scans.scans_service import ScansService

    _, paths = _resolve_project(registry, project_id)
    factory = _init_factory(paths.findings_db)
    return ScansService(
        run_repo=RunRepository(factory),
        project_id=project_id,
    )


def create_triage_service(
    registry: ProjectRegistryService,
    project_id: int,
) -> TriageService:
    """Build a TriageService for a project."""
    from application.triage.triage_service import TriageService

    _, paths = _resolve_project(registry, project_id)
    factory = _init_factory(paths.findings_db)
    return TriageService(
        run_repo=RunRepository(factory),
        triage_repo=TriageBatchRepository(factory),
        finding_repo=FindingRepository(factory),
        audit_repo=AuditRepository(factory),
    )


def create_url_list_service(
    registry: ProjectRegistryService,
    project_id: int,
) -> UrlListService:
    """Build a UrlListService for a project."""
    from application.url_inventory.service import UrlInventoryService
    from application.url_inventory.url_list_service import (
        UrlListService,
    )

    row, paths = _resolve_project(registry, project_id)
    findings_db_exists = paths.findings_db.exists()
    factory = _init_factory(paths.findings_db)
    url_repo = UrlFindingRepository(factory)
    project_repo = RepositoryRepository(factory)
    inventory = UrlInventoryService(url_repo)
    converter = EndpointFileConverter()
    return UrlListService(
        url_repo=url_repo,
        project_repo=project_repo,
        inventory=inventory,
        converter=converter,
        findings_db_exists=findings_db_exists,
        paths=paths,
        project_name=row.name,
    )
