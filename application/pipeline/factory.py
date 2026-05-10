"""PipelineFactory: creates a wired EventBus for a scan run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.pipeline.handlers import IngestHandler
from application.pipeline.strategies import (
    EnrichThenPersistStrategy,
    PersistOnlyStrategy,
    PostIngestStrategy,
)
from application.url_inventory.ingest_handler import UrlInventoryIngestHandler
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted

if TYPE_CHECKING:
    from application.locking.cancellation import CancellationToken
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.progress_reporter import ProgressReporter
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )
    from application.ports.scan_event_sink import ScanEventSink
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )


class PipelineFactory:
    """Creates a fully-wired EventBus for a single scan run."""

    @staticmethod
    def create(
        *,
        finding_repo: FindingRepositoryPort,
        repo_repo: ProjectRepoRepositoryPort,
        url_finding_repo: UrlFindingRepositoryPort,
        reporter: ProgressReporter | None = None,
        skip_enrichment: bool = False,
        project_id: int | None = None,
        event_sink: ScanEventSink | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> EventBus:
        """Return an EventBus wired with the post-ingest strategy."""
        bus = EventBus()

        ingest = IngestHandler(
            bus,
            finding_repo=finding_repo,
            repo_repo=repo_repo,
        )
        bus.subscribe(ToolCompleted, ingest.handle)

        strategy: PostIngestStrategy
        if skip_enrichment:
            strategy = PersistOnlyStrategy(
                finding_repo=finding_repo,
            )
        else:
            strategy = EnrichThenPersistStrategy(
                finding_repo=finding_repo,
                reporter=reporter,
                project_id=project_id,
                event_sink=event_sink,
                cancel_token=cancel_token,
            )

        bus.subscribe(IngestCompleted, strategy.handle)

        url_inventory = UrlInventoryIngestHandler(
            repo_repo=repo_repo,
            url_finding_repo=url_finding_repo,
        )
        bus.subscribe(ToolCompleted, url_inventory.handle)

        return bus
