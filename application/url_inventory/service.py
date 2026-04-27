"""UrlInventoryService — application-layer orchestrator for url_findings.

Wraps the ``UrlFindingRepository`` port with the project-aware operations
the rest of the codebase needs:

- ``ingest_scan_source(repo_id, run_id, tool, entries)`` — wipe-and-replace
  for a single ``(repo_id, tool)`` pair. Used by the Katana / Noir
  post-completion handler.
- ``ingest_user_file(repo_id, file_path, entries)`` — wipe-and-replace
  for a single user-uploaded source file. Used by the wizard's endpoint
  ingest path and by the Phase 9.3 multipart repo POST/PATCH endpoint.
- ``regenerate_artifacts(repo_id, repo_dir_key, base_url)`` — rebuild
  ``merged_urls.txt`` + ``merged_oas3.json`` from the current DB rows for
  one repo. Called JIT by ZAP/XSStrike/DalFox launchers and by the
  Phase 9.5 ``POST /url-list/regenerate`` endpoint.
- ``regenerate_artifacts_for_project(project_paths, active_repos)`` —
  iterate all active repos for a project; convenience for purge / batch
  regeneration.
- ``delete_for_project(project_id)`` — used by REPL ``purge``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from application.url_inventory.artifact_builder import write_artifacts

if TYPE_CHECKING:
    from core.project_paths import ProjectPaths
    from domain.url_inventory.entry import UrlFinding, UrlTool
    from infrastructure.store.repositories.url_findings import (
        UrlFindingRepository,
    )


class UrlInventoryService:
    """Application-layer URL inventory orchestrator."""

    def __init__(self, repo: UrlFindingRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Artifact regeneration
    # ------------------------------------------------------------------
    def regenerate_artifacts(
        self,
        *,
        repo_id: int,
        project_paths: ProjectPaths,
        repo_dir_key: str,
        base_url: str | None = None,
    ) -> tuple[str, str]:
        """Rebuild seeds.txt + merged_oas3.json for one repo from DB rows.

        ``repo_dir_key`` is the on-disk directory name under ``endpoints/``.
        Phase 9 callers should pass the repo's ``uuid`` (stable across
        renames); legacy callers may still pass the repo name.
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
        tuples — typically the caller maps active ``Repository`` entries
        to their DB id + uuid pair. Returns a list of
        ``(repo_id, seeds_path, oas3_path)`` tuples for the regenerated
        repos. Used by the Phase 9.5 ``POST /url-list/regenerate``
        endpoint and any batch-regeneration site.
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

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def delete_for_repo(self, repo_id: int) -> int:
        return self._repo.delete_for_repo(repo_id)

    def delete_for_project(self) -> int:
        """Wipe every ``url_findings`` row in the project-scoped DB.

        The repository handle is bound to a single project's
        ``findings.db``, so this is effectively a per-project nuke. Used
        by the REPL ``purge`` command's URL inventory cascade.
        """
        return self._repo.delete_all()

    def delete_all(self) -> int:
        return self._repo.delete_all()
