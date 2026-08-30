"""Continuous poller for Burp Organizer items."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from application.tools.burp.organizer_normalizer import (
    NormalizedHttp,
    normalize_http,
)

if TYPE_CHECKING:
    from application.mcp.ingest_service import McpIngestService
    from application.ports.finding_event_sink import FindingEventSink
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.organizer_state_repository import (
        OrganizerStateRepositoryPort,
    )
    from application.tools.burp.note_enrichment import (
        NoteClassification,
        NoteEnrichment,
    )
    from domain.locking.cancellation import CancellationToken
    from domain.tools.burp.mcp_ports import (
        OrganizerFetcherPort,
        OrganizerItem,
    )

logger = logging.getLogger(__name__)


class OrganizerPoller:
    """Poll Burp's Organizer and ingest new items."""

    def __init__(
        self,
        *,
        fetcher: OrganizerFetcherPort,
        state_repo: OrganizerStateRepositoryPort,
        ingest_service: McpIngestService,
        project_id: int,
        poll_interval: float = 30.0,
        note_enrichment: NoteEnrichment | None = None,
        finding_repo: FindingRepositoryPort | None = None,
        event_sink: FindingEventSink | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._state_repo = state_repo
        self._ingest = ingest_service
        self._project_id = project_id
        self._poll_interval = poll_interval
        self._enrichment = note_enrichment
        self._finding_repo = finding_repo
        self._event_sink = event_sink

    def run(self, cancel_token: CancellationToken) -> int:
        """Loop until cancellation. Returns total items ingested."""
        total = 0
        while not cancel_token.is_set():
            try:
                total += self.poll_once()
            except Exception:
                logger.exception("Poll cycle failed")
            cancel_token.wait(self._poll_interval)
        return total

    def poll_once(self) -> int:
        """Execute one poll cycle. Returns items ingested."""
        try:
            items = self._fetcher.fetch_items()
        except Exception:
            logger.exception("Failed to fetch Organizer items")
            return 0

        ingested_ids = self._state_repo.get_ingested_ids(self._project_id)
        new_items = [i for i in items if i.id not in ingested_ids]
        if not new_items:
            return 0

        result = self._ingest.create_scan_run(
            self._project_id,
            [],
            tool_ids=["burp_organizer"],
            domains=["web"],
        )
        run_id = result["run_id"]

        count = 0
        for item in new_items:
            normalized = normalize_http(item.request, item.response)
            classification = self._classify(item)
            payload = _build_payload(item, normalized, classification)
            result = self._ingest.submit_finding(
                run_id,
                payload,
                tool="burp_organizer",
                domain="web",
            )
            self._emit_created(result)
            self._state_repo.mark_ingested(self._project_id, item.id)
            count += 1
            logger.info("Ingested Organizer item %d", item.id)

        self._ingest.end_scan(self._project_id, run_id)
        logger.info(
            "Poll cycle complete: %d new items ingested",
            count,
        )
        return count

    def _emit_created(self, result: dict) -> None:
        """Emit a FindingCreated event if the sink is wired."""
        if not self._event_sink or not self._finding_repo:
            return
        finding_id = result.get("finding_id")
        if not finding_id:
            return
        finding = self._finding_repo.get_finding(finding_id)
        if not finding:
            return
        from domain.findings.events import FindingCreated

        self._event_sink.emit(
            FindingCreated(
                project_id=self._project_id,
                finding=finding,
                is_locked=False,
                lock_holder=None,
            )
        )

    def _classify(self, item: OrganizerItem) -> NoteClassification | None:
        note = item.notes.strip() if item.notes else ""
        if not note or self._enrichment is None:
            return None
        return self._enrichment.classify(note)


def _build_payload(
    item: OrganizerItem,
    normalized: NormalizedHttp,
    classification: NoteClassification | None,
) -> dict[str, Any]:
    """Convert an OrganizerItem to a finding submission payload."""
    notes = item.notes.strip() if item.notes else ""
    if classification is not None:
        severity = classification.severity
        cwe = [classification.cwe]
        finding_type = ["vulnerability"]
        vuln_type = classification.vulnerability_type
        description = notes or vuln_type
        title = f"{vuln_type}: {normalized.method} {normalized.url}".strip()
    else:
        severity = "informational"
        cwe = ["CWE-0"]
        finding_type = ["informational"]
        description = notes or "Burp Organizer item (no notes)"
        title = f"Organizer: {notes[:50]}" if notes else "Organizer: untitled"

    meta: dict[str, Any] = {
        "title": title,
        "owasp_name": "Unclassified",
        "remediation": "Review the captured request and response",
        "request": item.request,
        "response": item.response,
        "url": normalized.url,
        "method": normalized.method,
        "organizer_item_id": item.id,
        "organizer_status": item.status,
    }
    if normalized.host is not None:
        meta["host"] = normalized.host
    if normalized.status_code is not None:
        meta["status_code"] = normalized.status_code
    if classification is not None:
        meta["vulnerability_type"] = classification.vulnerability_type

    return {
        "segment": "web",
        "description": description,
        "severity": severity,
        "confidence": "confirmed",
        "cwe": cwe,
        "finding_type": finding_type,
        "rule_id": "burp_organizer",
        "meta": meta,
    }
