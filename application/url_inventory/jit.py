"""JIT-rebuild URL artifacts for scan-tool launchers.

ZAP / XSStrike / DalFox each need a freshly-rebuilt seeds file or merged
OAS3 document just before they run. Phase 9 dropped the persisted
``Repository.merged_seeds_path`` / ``merged_oas3_path`` fields in favour
of rebuilding the artifacts on demand from ``url_findings`` rows.

This helper is the single entry point for that rebuild — keeps the
SQLite plumbing out of the tool wrappers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.url_inventory.service import UrlInventoryService
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.url_findings import UrlFindingRepository

if TYPE_CHECKING:
    from core.config.schemas import Repository


def jit_rebuild_artifacts(
    base_path: str,
    project_name: str,
    repo: Repository,
) -> tuple[str | None, str | None]:
    """Rebuild ``merged_urls.txt`` + ``merged_oas3.json`` for *repo*.

    Returns ``(seeds_path, oas3_path)`` — both absolute paths — when
    ``url_findings`` has at least one row for the repo. When the repo
    has no rows (or no DB row at all, or no uuid yet), returns
    ``(None, None)`` so the caller can fall back to its quickscan path.
    """
    if not repo.uuid:
        return None, None

    paths = ProjectPaths.from_canonical(base_path, project_name)
    if not paths.findings_db.exists():
        return None, None

    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    repo_repo = RepositoryRepository(factory)
    db_row = repo_repo.get_by_uuid(repo.uuid)
    if db_row is None or db_row.deleted_at is not None:
        return None, None

    url_repo = UrlFindingRepository(factory)
    rows = url_repo.list_for_repo(db_row.id)
    if not rows:
        return None, None

    service = UrlInventoryService(url_repo)
    seeds_path, oas3_path = service.regenerate_artifacts(
        repo_id=db_row.id,
        project_paths=paths,
        repo_dir_key=repo.uuid,
        base_url=repo.base_urls[0] if repo.base_urls else None,
    )
    return seeds_path, oas3_path
