"""Pipeline handlers: IngestHandler, EnrichmentHandler, PersistenceHandler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.rag.enrichment import EnrichmentPipeline
from application.rag.ingestor import (
    ToolHandlerFactory,
    _is_test_path,
    _normalize_file_path,
)
from core.config.manager import ConfigManager
from domain.pipeline.events import (
    EnrichmentCompleted,
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from infrastructure.store import make_store
from infrastructure.store.repositories.findings_serial import compute_fingerprint

if TYPE_CHECKING:
    from rich.console import Console

    from application.rag.engine import RAGEngine

logger = logging.getLogger(__name__)


class BaseHandler:
    """Shared RAGEngine cache used by all pipeline handlers."""

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
                try:
                    repos = ConfigManager(event.base_path).load_repositories(
                        event.project_name
                    )
                except Exception:
                    repos = None
                if repos:
                    repo_test_dirs: dict[str, list[str]] = {
                        r.name: r.test_dirs for r in repos if r.test_dirs
                    }
                    filtered: list[dict] = []
                    for row in rows:
                        file_path: str = row.get("file_path", "") or ""
                        result_path = _normalize_file_path(
                            file_path, repos, repo_name=event.repo
                        )
                        if result_path is None:
                            logger.error(
                                "Excluding row with missing file path: "
                                "tool=%s rule_id=%s",
                                result.tool_name,
                                row.get("rule_id", ""),
                            )
                            continue
                        rel, repo_name = result_path
                        row["file_path"] = rel
                        if repo_name is not None:
                            row["repo"] = repo_name
                        if repo_name is not None and rel:
                            _tdirs = repo_test_dirs.get(repo_name, [])
                            if _tdirs and _is_test_path(rel, _tdirs):
                                logger.debug(
                                    "Excluding test-dir row: tool=%s path=%s",
                                    result.tool_name,
                                    rel,
                                )
                                continue
                        filtered.append(row)
                    rows = filtered

            _, finding_repo, _, _ = make_store(event.base_path, event.project_name)
            finding_repo.upsert_findings(event.run_id or 0, rows)
            fingerprints = [compute_fingerprint(row) for row in rows]
            sqlite_ids = finding_repo.get_ids_by_fingerprints(fingerprints)
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


class EnrichmentHandler(BaseHandler):
    """Handles IngestCompleted: runs LLM enrichment, emits EnrichmentCompleted."""

    def __init__(self, bus: EventBus, console: Console | None = None) -> None:
        super().__init__()
        self._bus = bus
        self._console = console

    def handle(self, event: IngestCompleted) -> None:
        if not event.ids:
            return

        _, finding_repo, _, _ = make_store(event.base_path, event.project_name)
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            console=self._console,
            base_path=event.base_path,
            run_id=event.run_id,
        )
        pipeline.enrich(event.ids)
        self._bus.dispatch(
            EnrichmentCompleted(
                ids=event.ids,
                partial_success=pipeline.had_errors,
                run_id=event.run_id,
                project_name=event.project_name,
                base_path=event.base_path,
            )
        )


class PersistenceHandler(BaseHandler):
    """Handles EnrichmentCompleted: persists enriched findings to SQLite."""

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        self._bus = bus

    def handle(self, event: EnrichmentCompleted) -> None:
        if event.run_id is None:
            return

        try:
            engine = self._get_engine(event.project_name, event.base_path)
        except Exception as exc:
            logger.warning("PersistenceHandler: RAGEngine init failed: %s", exc)
            return

        try:
            _, finding_repo, _, _ = make_store(event.base_path, event.project_name)
            findings_metadata: list[dict] = []
            for doc_id in event.ids:
                doc = engine.get_document_by_id(str(doc_id))
                if doc is not None:
                    findings_metadata.append(doc["metadata"])
            if findings_metadata:
                finding_repo.upsert_findings(event.run_id, findings_metadata)
        except Exception as exc:
            logger.error("PersistenceHandler: persistence error: %s", exc)
