"""Post-ingest pipeline strategies.

Strategy pattern for what happens after findings are ingested to SQLite:

- ``EnrichThenPersistStrategy``: runs LLM enrichment, then writes to ChromaDB.
- ``PersistOnlyStrategy``: writes directly to ChromaDB, skipping enrichment.

Both strategies subscribe to ``IngestCompleted`` on the EventBus. Neither emits
a further event — they are terminal pipeline steps.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from application.pipeline.handlers import BaseHandler
from application.ports.scan_event_sink import NullScanEventSink, ScanEventSink
from application.rag.enrichment import EnrichmentPipeline
from infrastructure.store import make_store

if TYPE_CHECKING:
    from rich.console import Console

    from application.locking.cancellation import CancellationToken


from domain.pipeline.events import IngestCompleted

logger = logging.getLogger(__name__)


@runtime_checkable
class PostIngestStrategy(Protocol):
    """Defines the post-ingest step: what happens to findings after SQLite write."""

    def handle(self, event: IngestCompleted) -> None: ...


class EnrichThenPersistStrategy(BaseHandler):
    """Run LLM enrichment on ingested findings, then persist to ChromaDB."""

    def __init__(
        self,
        console: Console | None = None,
        project_id: int | None = None,
        event_sink: ScanEventSink | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> None:
        super().__init__()
        self._console = console
        self._project_id = project_id
        self._event_sink: ScanEventSink = event_sink or NullScanEventSink()
        self._cancel_token = cancel_token

    def handle(self, event: IngestCompleted) -> None:
        if not event.ids:
            return

        _, finding_repo, _, _ = make_store(event.base_path, event.project_name)
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            console=self._console,
            base_path=event.base_path,
            run_id=event.run_id,
            project_id=self._project_id,
            event_sink=self._event_sink,
            cancel_token=self._cancel_token,
        )
        pipeline.enrich(event.ids)
        self._persist_to_chromadb(event.ids, event.project_name, event.base_path)


class PersistOnlyStrategy(BaseHandler):
    """Persist ingested findings directly to ChromaDB, skipping LLM enrichment."""

    def __init__(self, console: Console | None = None) -> None:
        super().__init__()
        self._console = console

    def handle(self, event: IngestCompleted) -> None:
        if not event.ids:
            return
        self._persist_to_chromadb(event.ids, event.project_name, event.base_path)
