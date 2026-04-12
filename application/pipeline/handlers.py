"""Pipeline handlers: IngestHandler (and BaseHandler with shared ChromaDB logic)."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from application.rag.ingestor import (
    ToolHandlerFactory,
    filter_code_rows,
)
from core.config.manager import ConfigManager
from domain.pipeline.events import (
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from domain.pipeline.fingerprint import compute_fingerprint
from infrastructure.store import make_store

if TYPE_CHECKING:
    from rich.console import Console

    from application.rag.engine import RAGEngine

logger = logging.getLogger(__name__)


class BaseHandler:
    """Shared RAGEngine cache and ChromaDB persistence used by pipeline steps."""

    def __init__(self) -> None:
        self._engines: dict[str, RAGEngine] = {}

    def _get_engine(self, project_name: str, base_path: str) -> RAGEngine:
        key = f"{project_name}:{base_path}"
        if key not in self._engines:
            from application.rag.engine import RAGEngine

            self._engines[key] = RAGEngine(
                project_name=project_name,
                base_path=base_path,
            )
        return self._engines[key]

    def _persist_to_chromadb(
        self, ids: list[int], project_name: str, base_path: str
    ) -> None:
        """Write findings to ChromaDB by their SQLite IDs."""
        try:
            engine = self._get_engine(project_name, base_path)
        except Exception as exc:
            logger.warning("%s: RAGEngine init failed: %s", type(self).__name__, exc)
            return

        try:
            _, finding_repo, _, _ = make_store(base_path, project_name)
            rows = finding_repo.get_by_ids(ids)
            grouped: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
            for row in rows:
                grouped[(row["tool"], row["profile"])].append(row)
            for (tool, profile), group_rows in grouped.items():
                engine.delete_findings(tool, profile)
                handler = ToolHandlerFactory.load(tool)
                if handler is None:
                    continue
                texts = [
                    f"Repository: {profile} | {handler.render(row)}"
                    for row in group_rows
                ]
                metadatas = [{"tool": tool, "profile": profile} for _ in group_rows]
                doc_ids = [str(row["id"]) for row in group_rows]
                engine.add_documents(texts=texts, metadatas=metadatas, ids=doc_ids)
        except Exception as exc:
            logger.error("%s: ChromaDB write error: %s", type(self).__name__, exc)


class IngestHandler(BaseHandler):
    """Handles ToolCompleted: normalizes findings to SQLite, emits IngestCompleted."""

    def __init__(self, bus: EventBus, console: Console | None = None) -> None:
        super().__init__()
        self._bus = bus
        self._console = console

    def handle(self, event: ToolCompleted) -> None:
        result = event.result
        if (
            not result.success
            or not result.parsed_data
            or "error" in result.parsed_data
        ):
            self._bus.dispatch(
                IngestCompleted(
                    ids=[],
                    failed_tools=[],
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )
            return

        sqlite_ids: list[int] = []
        failed_tools: list[str] = []
        try:
            handler = ToolHandlerFactory.load(result.tool_name)
            if handler is None:
                self._bus.dispatch(
                    IngestCompleted(
                        ids=[],
                        failed_tools=[],
                        run_id=event.run_id,
                        project_name=event.project_name,
                        base_path=event.base_path,
                    )
                )
                return

            rows: list[dict] = handler.normalize(result, event.profile)

            if handler.domain == "code":
                if handler.segment in ("sca", "web"):
                    # SCA and web-segment code tools (e.g. Noir) have no file
                    # path to normalise; set repo directly from execution context.
                    if event.repo:
                        for row in rows:
                            row.setdefault("repo", event.repo)
                else:
                    try:
                        repos = ConfigManager(event.base_path).load_repositories(
                            event.project_name
                        )
                    except Exception:
                        repos = None
                    rows = filter_code_rows(rows, repos, event.repo, result.tool_name)
            else:
                # web/network tools: set repo from execution context
                if event.repo:
                    for row in rows:
                        row.setdefault("repo", event.repo)

            _, finding_repo, _, _ = make_store(event.base_path, event.project_name)
            finding_repo.insert_findings(event.run_id or 0, rows)
            fingerprints = [compute_fingerprint(row) for row in rows]
            sqlite_ids = finding_repo.get_ids_by_fingerprints(
                fingerprints, run_id=event.run_id or 0
            )
        except Exception as exc:
            logger.error(
                "IngestHandler: ingestion failed for %s: %s",
                result.tool_name,
                exc,
            )
            failed_tools.append(result.tool_name)

        self._bus.dispatch(
            IngestCompleted(
                ids=sqlite_ids,
                failed_tools=failed_tools,
                run_id=event.run_id,
                project_name=event.project_name,
                base_path=event.base_path,
            )
        )
