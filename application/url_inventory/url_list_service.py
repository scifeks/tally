"""Application service for the URL list web surface."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from application.url_inventory.ports import UrlProviderContext
from application.url_inventory.providers.user_file import UserFileProvider
from application.url_inventory.service import UrlInventoryService
from core.project_paths import ProjectPaths

if TYPE_CHECKING:
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from application.ports.url_source_converter import UrlSourceConverterPort
    from core.config.schemas import Repository


class ProjectNotFound(LookupError):
    """Raised when a project_id has no active row in the registry."""


class UrlListService:
    """URL list facade bound to a single project."""

    def __init__(
        self,
        url_repo: UrlFindingRepositoryPort,
        project_repo: ProjectRepoRepositoryPort,
        inventory: UrlInventoryService,
        *,
        converter: UrlSourceConverterPort,
        findings_db_exists: bool,
        paths: ProjectPaths,
        project_name: str,
    ) -> None:
        self._url_repo = url_repo
        self._project_repo = project_repo
        self._inventory = inventory
        self._converter = converter
        self._findings_db_exists = findings_db_exists
        self._paths = paths
        self._project_name = project_name

    @property
    def url_repo(self) -> UrlFindingRepositoryPort:
        return self._url_repo

    @property
    def inventory(self) -> UrlInventoryService:
        return self._inventory

    def repo_name_lookup(self) -> dict[int, str]:
        """Build ``{repo_id: repo_name}`` for the project's active repos.

        Returns ``{}`` when the findings DB has not been created yet
        or when the underlying read raises. The defensive shape is
        load-bearing for the URL list routes.
        """
        if not self._findings_db_exists:
            return {}
        try:
            return {
                r.id: r.name
                for r in self._project_repo.list_active()
                if r.name and isinstance(r.id, int)
            }
        except Exception:
            return {}

    def count_active_url_findings(self) -> int:
        """Count url_findings rows whose owning repo is not soft-deleted.

        Returns 0 when the findings DB has not been created yet or
        when the underlying read raises.
        """
        if not self._findings_db_exists:
            return 0
        try:
            return self._url_repo.count_active()
        except Exception:
            return 0

    def count_all_url_findings(self) -> int:
        """Count every url_findings row, regardless of repo state.

        Returns 0 when the findings DB has not been created yet or
        when the underlying read raises. Used by the REPL ``purge``
        command to decide whether the full-wipe path has any
        url_findings work to do.
        """
        if not self._findings_db_exists:
            return 0
        try:
            return self._url_repo.count_all()
        except Exception:
            return 0

    def delete_url_findings_for_tools(self, tools: list[str]) -> int:
        """Delete url_findings rows whose ``tool`` is in *tools*.

        Returns 0 when the findings DB does not yet exist, when
        *tools* is empty, or on any underlying error. Used by the
        per-tool branch of the REPL ``purge`` command for Katana /
        Noir cleanup.
        """
        if not self._findings_db_exists or not tools:
            return 0
        try:
            return self._url_repo.delete_for_tools(tools)
        except Exception:
            return 0

    def purge_all_url_findings(self) -> int:
        """Wipe every url_findings row for the project.

        Returns 0 when the findings DB does not yet exist or on
        any underlying error. Delegates to the wrapped
        ``UrlInventoryService`` so the REPL ``purge`` command does
        not need to import the inventory service directly.
        """
        if not self._findings_db_exists:
            return 0
        try:
            return self._inventory.delete_for_project()
        except Exception:
            return 0

    def repo_has_url_findings(self, repo_id: int) -> bool:
        """Return True when *repo_id* has any persisted url_findings rows.

        Returns False when the findings DB has not been created yet or
        when the underlying read raises. Mirrors the defensive shape of
        ``count_active_url_findings``.
        """
        if not self._findings_db_exists:
            return False
        try:
            return bool(self._url_repo.list_for_repo(repo_id))
        except Exception:
            return False

    def ingest_uploaded_endpoint_file(
        self,
        *,
        repo: Repository,
        repo_id: int,
        filename: str,
        contents: bytes,
    ) -> None:
        """Persist *contents* under ``endpoints/<repo_name>-<epoch>/`` and ingest.

        Each call creates a fresh sibling dir so prior uploads accumulate as
        history. Records the most-recent path on
        ``repositories.url_seed_file``, runs ``UserFileProvider`` against the
        file, and ingests the rows via the wrapped ``UrlInventoryService``.
        """
        epoch = time.time_ns()
        upload_dir = self._paths.seed_upload_dir(repo.name, epoch)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / filename
        dest.write_bytes(contents)

        self._project_repo.set_url_seed_file(repo_id, str(dest))

        ctx = UrlProviderContext(
            repo=repo,
            repo_id=repo_id,
            base_path=str(self._paths.root.parent.parent),
            project_name=self._project_name,
            run_id=None,
        )
        entries = list(
            UserFileProvider(self._converter).provide(ctx, file_path=str(dest))
        )
        self._inventory.ingest_user_file(
            repo_id=repo_id,
            file_path=str(dest),
            entries=entries,
        )
