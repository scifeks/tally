"""Pipeline handlers: IngestHandler, EnrichmentHandler, PersistenceHandler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.pipeline.events import (
    EnrichmentCompleted,
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from core.rag.enrichment import EnrichmentPipeline
from core.rag.ingestor import FindingIngestor
from core.store.sqlite_store import SQLiteStore

if TYPE_CHECKING:
    from rich.console import Console

    from core.rag.engine import RAGEngine

logger = logging.getLogger(__name__)


class BaseHandler:
    """Shared RAGEngine cache used by all pipeline handlers."""

    def __init__(self) -> None:
        self._engines: dict[str, RAGEngine] = {}

    def _get_engine(self, project_name: str, base_path: str) -> RAGEngine:
        key = f"{project_name}:{base_path}"
        if key not in self._engines:
            from core.rag.engine import RAGEngine

            self._engines[key] = RAGEngine(
                project_name=project_name,
                base_path=base_path,
            )
        return self._engines[key]


class IngestHandler(BaseHandler):
    """Handles ToolCompleted: ingests findings into ChromaDB, emits IngestCompleted."""

    def __init__(self, bus: EventBus, console: Console | None = None) -> None:
        super().__init__()
        self._bus = bus
        self._console = console

    def handle(self, event: ToolCompleted) -> None:
        try:
            engine = self._get_engine(event.project_name, event.base_path)
        except Exception as exc:
            logger.warning("IngestHandler: RAGEngine init failed: %s", exc)
            self._bus.dispatch(
                IngestCompleted(
                    doc_ids=[],
                    failed_tools=[],
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )
            return

        result = event.result
        if (
            not result.success
            or not result.parsed_data
            or "error" in result.parsed_data
        ):
            self._bus.dispatch(
                IngestCompleted(
                    doc_ids=[],
                    failed_tools=[],
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )
            return

        doc_ids: list[str] = []
        failed_tools: list[str] = []
        try:
            ingestor = FindingIngestor(engine, event.project_name)
            doc_ids = ingestor.ingest_tool_output(result, profile=event.profile)
        except Exception as exc:
            logger.error(
                "IngestHandler: ingestion failed for %s: %s", result.tool_name, exc
            )
            failed_tools.append(result.tool_name)

        self._bus.dispatch(
            IngestCompleted(
                doc_ids=doc_ids,
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
        if not event.doc_ids:
            return

        try:
            engine = self._get_engine(event.project_name, event.base_path)
        except Exception as exc:
            logger.warning("EnrichmentHandler: RAGEngine init failed: %s", exc)
            self._bus.dispatch(
                EnrichmentCompleted(
                    doc_ids=event.doc_ids,
                    partial_success=False,
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )
            return

        try:
            pipeline = EnrichmentPipeline(engine, console=self._console)
            pipeline.enrich(event.doc_ids)
        except Exception as exc:
            logger.error("EnrichmentHandler: enrichment error: %s", exc)
            self._bus.dispatch(
                EnrichmentCompleted(
                    doc_ids=event.doc_ids,
                    partial_success=False,
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )
            return

        self._bus.dispatch(
            EnrichmentCompleted(
                doc_ids=event.doc_ids,
                partial_success=True,
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
            sqlite_store = SQLiteStore(event.base_path, event.project_name)
            findings_metadata: list[dict] = []
            for doc_id in event.doc_ids:
                doc = engine.get_document_by_id(doc_id)
                if doc is not None:
                    findings_metadata.append(doc["metadata"])
            if findings_metadata:
                sqlite_store.upsert_findings(event.run_id, findings_metadata)
        except Exception as exc:
            logger.error("PersistenceHandler: persistence error: %s", exc)
