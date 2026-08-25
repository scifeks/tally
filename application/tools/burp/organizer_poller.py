"""Continuous poller for Burp Organizer items."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.mcp.ingest_service import McpIngestService
    from application.ports.organizer_state_repository import (
        OrganizerStateRepositoryPort,
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
    ) -> None:
        self._fetcher = fetcher
        self._state_repo = state_repo
        self._ingest = ingest_service
        self._project_id = project_id
        self._poll_interval = poll_interval

    def run(self, cancel_token: CancellationToken) -> int:
        """Loop until cancellation. Returns total items ingested."""
        total = 0
        while not cancel_token.is_set():
            total += self.poll_once()
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
            payload = _build_payload(item)
            self._ingest.submit_finding(
                run_id,
                payload,
                tool="burp_organizer",
                domain="web",
            )
            self._state_repo.mark_ingested(self._project_id, item.id)
            count += 1
            logger.info("Ingested Organizer item %d", item.id)

        self._ingest.end_scan(self._project_id, run_id)
        logger.info(
            "Poll cycle complete: %d new items ingested",
            count,
        )
        return count


def _build_payload(item: OrganizerItem) -> dict[str, Any]:
    """Convert an OrganizerItem to a finding submission payload."""
    notes = item.notes.strip() if item.notes else ""
    description = notes or "Burp Organizer item (no notes)"
    title = f"Organizer: {notes[:50]}" if notes else "Organizer: untitled"
    return {
        "segment": "web",
        "description": description,
        "severity": "informational",
        "confidence": "confirmed",
        "cwe": ["CWE-0"],
        "finding_type": ["informational"],
        "rule_id": "burp_organizer",
        "meta": {
            "title": title,
            "owasp_name": "Unclassified",
            "remediation": ("Review the captured request and response"),
            "request": item.request,
            "response": item.response,
            "organizer_item_id": item.id,
            "organizer_status": item.status,
        },
    }
