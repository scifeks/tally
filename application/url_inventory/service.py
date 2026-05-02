"""Application-layer orchestrator for url_findings operations.

Provides:
- Ingest of scan-source (Katana/Noir) and user-file data.
- Artifact regeneration (merged_urls.txt and merged_oas3.json) from DB rows.
- Project-scoped cleanup (used by REPL purge).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from application.url_inventory.artifact_builder import write_artifacts

if TYPE_CHECKING:
    from application.ports.url_finding_repository import UrlFindingRepositoryPort
    from core.project_paths import ProjectPaths
    from domain.url_inventory.entry import UrlFinding, UrlTool


class UrlInventoryService:
    """Application-layer URL inventory orchestrator."""

    def __init__(self, repo: UrlFindingRepositoryPort) -> None:
        self._repo = repo

    # Ingest
    def ingest_scan_source(
        self,
        *,
        repo_id: int,
        run_id: int | None,
        tool: UrlTool,
        entries: Iterable[UrlFinding],
    ) -> int:
        """Replace the SCAN-source rows for ``(repo_id, tool)`` with *entries*.

        Wipe-and-replace: the SQLite unique index handles dedup within the
        new batch; the explicit DELETE removes stale rows from prior runs.
        Returns the count of rows actually inserted.
        """
        del run_id  # carried on each entry; service only needs the tool here.
        self._repo.delete_for_repo_and_tool(repo_id, tool)
        return self._repo.insert_many(entries)

    def ingest_user_file(
        self,
        *,
        repo_id: int,
        file_path: str,
        entries: Iterable[UrlFinding],
    ) -> int:
        """Replace USER-source rows for ``(repo_id, file_path)`` with *entries*."""
        self._repo.delete_for_user_file(repo_id, file_path)
        return self._repo.insert_many(entries)

    # Artifact regeneration
    def regenerate_artifacts(
        self,
        *,
        repo_id: int,
        project_paths: ProjectPaths,
        repo_dir_key: str,
        base_url: str | None = None,
    ) -> tuple[str, str]:
        """Rebuild merged_urls.txt and merged_oas3.json from DB rows.

        ``repo_dir_key`` is the on-disk directory name under ``endpoints/``.
        """
        rows = self._repo.list_for_repo(repo_id)
        return write_artifacts(
            project_paths,
            repo_dir_key,
            rows,
            base_url=base_url,
        )

    def regenerate_artifacts_for_project(
        self,
        *,
        project_paths: ProjectPaths,
        active_repos: Iterable[tuple[int, str]],
        base_url: str | None = None,
    ) -> list[tuple[int, str, str]]:
        """Rebuild artifacts for every active repo in a project.

        ``active_repos`` is an iterable of ``(repo_id, repo_dir_key)``
        tuples. Returns a list of ``(repo_id, seeds_path, oas3_path)``
        tuples for the regenerated repos.
        """
        out: list[tuple[int, str, str]] = []
        for repo_id, repo_dir_key in active_repos:
            seeds_path, oas3_path = self.regenerate_artifacts(
                repo_id=repo_id,
                project_paths=project_paths,
                repo_dir_key=repo_dir_key,
                base_url=base_url,
            )
            out.append((repo_id, seeds_path, oas3_path))
        return out

    # Cleanup
    def delete_for_repo(self, repo_id: int) -> int:
        return self._repo.delete_for_repo(repo_id)

    def delete_for_project(self) -> int:
        """Wipe every ``url_findings`` row in the project-scoped DB."""
        return self._repo.delete_all()

    def delete_all(self) -> int:
        return self._repo.delete_all()
