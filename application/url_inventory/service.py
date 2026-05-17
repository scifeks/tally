"""Application-layer orchestrator for url_findings operations.

Provides:
- Ingest of scan-source (Katana/Noir) and user-file data.
- Artifact regeneration (merged_urls.txt and merged_oas3.json) from DB rows.
- Project-scoped cleanup (used by REPL purge).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from application.url_inventory.artifact_builder import write_artifacts
from domain.url_inventory.entry import UrlTool

if TYPE_CHECKING:
    from application.ports.url_finding_repository import UrlFindingRepositoryPort
    from core.project_paths import ProjectPaths
    from domain.url_inventory.entry import UrlFinding


def _terminal_segment(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1].lower()


def _merge_query_params(
    katana_meta: dict[str, Any],
    noir_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Return updated katana_meta with unique Noir query params, or None."""
    noir_op = noir_meta.get("original_file")
    if not isinstance(noir_op, dict):
        return None
    noir_params = noir_op.get("parameters")
    if not isinstance(noir_params, list):
        return None
    noir_query = [
        p for p in noir_params if isinstance(p, dict) and p.get("in") == "query"
    ]
    if not noir_query:
        return None

    katana_op = katana_meta.get("original_file")
    if not isinstance(katana_op, dict):
        katana_op = {}
    existing = katana_op.get("parameters")
    if not isinstance(existing, list):
        existing = []
    existing_names = {
        p.get("name")
        for p in existing
        if isinstance(p, dict) and p.get("in") == "query"
    }

    new_params = [p for p in noir_query if p.get("name") not in existing_names]
    if not new_params:
        return None

    merged_op = dict(katana_op)
    merged_op["parameters"] = list(existing) + new_params
    result = dict(katana_meta)
    result["original_file"] = merged_op
    return result


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

    # Reconciliation

    def reconcile_noir_with_katana(self, repo_id: int) -> int:
        """Drop Noir findings that duplicate a Katana finding.

        Matches by terminal path segment + HTTP method; unique Noir
        query parameters are merged into the surviving Katana entry.
        """
        katana, _ = self._repo.list_paginated(
            repo_id=[repo_id], tool=UrlTool.KATANA, limit=10_000
        )
        if not katana:
            return 0
        noir, _ = self._repo.list_paginated(
            repo_id=[repo_id], tool=UrlTool.NOIR, limit=10_000
        )
        if not noir:
            return 0

        katana_by_key: dict[tuple[str, str], UrlFinding] = {}
        for f in katana:
            seg = _terminal_segment(f.path)
            if seg:
                katana_by_key[(seg, f.method.upper())] = f

        keepers: list[UrlFinding] = []
        dropped = 0
        for nf in noir:
            seg = _terminal_segment(nf.path)
            key = (seg, nf.method.upper()) if seg else None
            kf = katana_by_key.get(key) if key else None
            if kf is None:
                keepers.append(nf)
                continue
            dropped += 1
            updated = _merge_query_params(kf.meta, nf.meta)
            if updated is not None and kf.id is not None:
                self._repo.update_meta(kf.id, updated)

        if dropped == 0:
            return 0
        self._repo.delete_for_repo_and_tool(repo_id, UrlTool.NOIR)
        if keepers:
            self._repo.insert_many(keepers)
        return dropped

    # Cleanup
    def delete_for_repo(self, repo_id: int) -> int:
        return self._repo.delete_for_repo(repo_id)

    def delete_for_project(self) -> int:
        """Wipe every ``url_findings`` row in the project-scoped DB."""
        return self._repo.delete_all()

    def delete_all(self) -> int:
        return self._repo.delete_all()
