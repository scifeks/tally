"""Rebuild URL artifacts just-in-time for scan-tool launchers.

ZAP, XSStrike, and DalFox each need freshly-rebuilt seeds files or merged
OAS3 documents just before they run. The on-disk artifacts are rebuilt
on demand from ``url_findings`` rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.url_inventory.service import UrlInventoryService
from core.project_paths import ProjectPaths

if TYPE_CHECKING:
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from core.config.schemas import Repository


def jit_rebuild_artifacts(
    base_path: str,
    project_name: str,
    repo: Repository,
    url_finding_repo: UrlFindingRepositoryPort,
) -> tuple[str | None, str | None]:
    """Rebuild merged_urls.txt and merged_oas3.json for the repo.

    Returns (seeds_path, oas3_path) as absolute paths when the repo has
    url_findings rows. Returns (None, None) if the repo has no rows or
    no DB id yet, so the caller can fall back to its quickscan path.
    """
    if repo.id is None:
        return None, None

    paths = ProjectPaths.from_canonical(base_path, project_name)
    if not paths.findings_db.exists():
        return None, None

    rows = url_finding_repo.list_for_repo(repo.id)
    if not rows:
        return None, None

    service = UrlInventoryService(url_finding_repo)
    seeds_path, oas3_path = service.regenerate_artifacts(
        repo_id=repo.id,
        project_paths=paths,
        repo_dir_key=str(repo.id),
        base_url=repo.base_urls[0] if repo.base_urls else None,
    )
    return seeds_path, oas3_path
