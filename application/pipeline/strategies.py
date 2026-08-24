"""Post-ingest pipeline strategies.

Strategy pattern for what happens after findings are ingested to SQLite:

- ``EnrichThenPersistStrategy``: runs LLM enrichment, then indexes into
  the vector index.
- ``PersistOnlyStrategy``: indexes into the vector index, skipping
  enrichment.

Both strategies subscribe to ``IngestCompleted`` on the EventBus. Neither
emits a further event; they are terminal pipeline steps.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from application.pipeline.handlers import BaseHandler
from application.ports.progress_reporter import ProgressReporter
from application.ports.scan_event_sink import NullScanEventSink, ScanEventSink
from application.rag.enrichment import EnrichmentPipeline
from domain.pipeline.events import IngestCompleted

if TYPE_CHECKING:
    from application.locking.cancellation import CancellationToken
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.rag.finding_indexer import FindingIndexer

logger = logging.getLogger(__name__)


@runtime_checkable
class PostIngestStrategy(Protocol):
    """Defines the post-ingest step: what happens to findings after SQLite write."""

    def handle(self, event: IngestCompleted) -> None: ...


class EnrichThenPersistStrategy(BaseHandler):
    """Run LLM enrichment, then index findings into the vector index."""

    def __init__(
        self,
        finding_repo: FindingRepositoryPort,
        indexer: FindingIndexer,
        reporter: ProgressReporter | None = None,
        project_id: int | None = None,
        event_sink: ScanEventSink | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> None:
        super().__init__(finding_repo=finding_repo)
        self._indexer = indexer
        self._reporter = reporter
        self._project_id = project_id
        self._event_sink: ScanEventSink = event_sink or NullScanEventSink()
        self._cancel_token = cancel_token

    def handle(self, event: IngestCompleted) -> None:
        if not event.ids:
            return

        pipeline = EnrichmentPipeline(
            finding_repo=self._finding_repo,
            reporter=self._reporter,
            base_path=event.base_path,
            run_id=event.run_id,
            project_id=self._project_id,
            event_sink=self._event_sink,
            cancel_token=self._cancel_token,
        )
        pipeline.enrich(event.ids)
        try:
            kb = self._get_knowledge_base(event.project_name, event.base_path)
        except Exception as exc:
            logger.warning(
                "EnrichThenPersistStrategy: knowledge base init failed: %s",
                exc,
            )
            return
        try:
            self._indexer.index_findings(
                kb, event.ids, caller_label="EnrichThenPersistStrategy"
            )
        except Exception as exc:
            logger.error(
                "EnrichThenPersistStrategy: vector index write failed: %s",
                exc,
            )


class PersistOnlyStrategy(BaseHandler):
    """Index findings into the vector index, skipping enrichment."""

    def __init__(
        self,
        finding_repo: FindingRepositoryPort,
        indexer: FindingIndexer,
    ) -> None:
        super().__init__(finding_repo=finding_repo)
        self._indexer = indexer

    def handle(self, event: IngestCompleted) -> None:
        if not event.ids:
            return
        try:
            kb = self._get_knowledge_base(event.project_name, event.base_path)
        except Exception as exc:
            logger.warning(
                "PersistOnlyStrategy: knowledge base init failed: %s",
                exc,
            )
            return
        self._indexer.index_findings(kb, event.ids, caller_label="PersistOnlyStrategy")
