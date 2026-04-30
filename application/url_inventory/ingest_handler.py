"""``UrlInventoryIngestHandler`` — scan-side URL ingest for Phase 9.

Subscribes to ``ToolCompleted``. For Katana / Noir, locates the OAS3
file produced by the wrapper (exposed via ``ToolResult.output_files['oas3']``),
parses it through the matching ``UrlListProvider``, persists the rows into
``url_findings`` via ``UrlInventoryService.ingest_scan_source``, and JIT-rebuilds
``merged_urls.txt`` + ``merged_oas3.json`` so downstream DAST tools see the
new URLs without re-reading source files.

Replaces the legacy ``application/pipeline/url_handlers.py`` chain entirely.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.url_inventory.ports import UrlProviderContext
from application.url_inventory.providers import KatanaProvider, NoirProvider
from application.url_inventory.service import UrlInventoryService
from core.project_paths import ProjectPaths
from domain.url_inventory.entry import UrlTool
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.url_findings import UrlFindingRepository

if TYPE_CHECKING:
    from domain.pipeline.events import ToolCompleted

logger = logging.getLogger(__name__)


_TOOL_PROVIDER_MAP: dict[str, tuple[type, UrlTool]] = {
    "katana": (KatanaProvider, UrlTool.KATANA),
    "noir": (NoirProvider, UrlTool.NOIR),
}


class UrlInventoryIngestHandler:
    """Bus handler that routes Katana / Noir output into ``url_findings``."""

    def handle(self, event: ToolCompleted) -> None:
        tool_name = (event.result.tool_name or "").lower()
        provider_cls_tool = _TOOL_PROVIDER_MAP.get(tool_name)
        if provider_cls_tool is None:
            return
        if not event.result.success:
            return
        if event.repo is None:
            return

        oas3_path = event.result.output_files.get("oas3")
        if oas3_path is None or not oas3_path.exists():
            logger.debug(
                "UrlInventoryIngestHandler: %s produced no OAS3 file for %s",
                tool_name,
                event.repo,
            )
            return

        try:
            paths = ProjectPaths.from_canonical(event.base_path, event.project_name)
            paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
            factory = ConnectionFactory(paths.findings_db)
            factory.init_schema()
            repo_repo = RepositoryRepository(factory)
            repo = repo_repo.get_by_name(event.repo)
            if repo is None or repo.id is None:
                logger.warning(
                    "UrlInventoryIngestHandler: no active repositories row "
                    "for %r in project %r; skipping ingest",
                    event.repo,
                    event.project_name,
                )
                return
            repo_id = repo.id

            provider_cls, url_tool = provider_cls_tool
            ctx = UrlProviderContext(
                repo=repo,
                repo_id=repo_id,
                base_path=event.base_path,
                project_name=event.project_name,
                run_id=event.run_id,
            )
            provider = provider_cls()
            entries = list(provider.provide(ctx, file_path=str(oas3_path)))

            url_repo = UrlFindingRepository(factory)
            service = UrlInventoryService(url_repo)
            service.ingest_scan_source(
                repo_id=repo_id,
                run_id=event.run_id,
                tool=url_tool,
                entries=entries,
            )
            service.regenerate_artifacts(
                repo_id=repo_id,
                project_paths=paths,
                repo_dir_key=str(repo_id),
            )
        except Exception:
            logger.exception(
                "UrlInventoryIngestHandler: ingest failed for %s/%s",
                event.project_name,
                event.repo,
            )
