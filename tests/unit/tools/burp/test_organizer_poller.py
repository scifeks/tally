"""Unit tests for OrganizerPoller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.tools.burp.note_enrichment import NoteClassification
from application.tools.burp.organizer_poller import OrganizerPoller
from domain.locking.cancellation import CancellationToken
from domain.tools.burp.mcp_ports import OrganizerItem


def _item(id: int, notes: str = "", request: str = "GET / HTTP/1.1") -> OrganizerItem:
    return OrganizerItem(
        id=id,
        status="New",
        request=request,
        response="HTTP/1.1 200 OK",
        notes=notes,
    )


@pytest.fixture()
def fetcher() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def state_repo() -> MagicMock:
    mock = MagicMock()
    mock.get_ingested_ids.return_value = set()
    return mock


@pytest.fixture()
def ingest() -> MagicMock:
    mock = MagicMock()
    mock.create_scan_run.return_value = {"run_id": 1}
    mock.submit_finding.return_value = {
        "finding_id": 1,
        "status": "accepted",
    }
    return mock


@pytest.fixture()
def poller(
    fetcher: MagicMock,
    state_repo: MagicMock,
    ingest: MagicMock,
) -> OrganizerPoller:
    return OrganizerPoller(
        fetcher=fetcher,
        state_repo=state_repo,
        ingest_service=ingest,
        project_id=1,
    )


class TestPollOnce:
    def test_ingests_new_items(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        state_repo: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [
            _item(1, notes="found XSS"),
            _item(2, notes="IDOR via user ID"),
        ]
        count = poller.poll_once()

        assert count == 2
        assert ingest.create_scan_run.call_count == 1
        assert ingest.submit_finding.call_count == 2
        assert ingest.end_scan.call_count == 1
        assert state_repo.mark_ingested.call_count == 2
        state_repo.mark_ingested.assert_any_call(1, 1)
        state_repo.mark_ingested.assert_any_call(1, 2)

    def test_skips_already_ingested(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        state_repo: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [
            _item(1),
            _item(2),
            _item(3),
        ]
        state_repo.get_ingested_ids.return_value = {1, 2}

        count = poller.poll_once()
        assert count == 1
        assert ingest.submit_finding.call_count == 1

    def test_empty_list_skips_scan_run(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = []
        count = poller.poll_once()

        assert count == 0
        ingest.create_scan_run.assert_not_called()

    def test_all_ingested_skips_scan_run(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        state_repo: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [_item(1)]
        state_repo.get_ingested_ids.return_value = {1}

        count = poller.poll_once()
        assert count == 0
        ingest.create_scan_run.assert_not_called()

    def test_connection_failure_returns_zero(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.side_effect = ConnectionError("refused")
        count = poller.poll_once()
        assert count == 0
        ingest.create_scan_run.assert_not_called()

    def test_passes_web_segment_and_confirmed(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [
            _item(1, notes="test note"),
        ]
        poller.poll_once()

        payload = ingest.submit_finding.call_args[0][1]
        assert payload["segment"] == "web"
        assert payload["confidence"] == "confirmed"

    def test_uses_burp_organizer_tool_id(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [_item(1)]
        poller.poll_once()

        ingest.create_scan_run.assert_called_once()
        kwargs = ingest.create_scan_run.call_args
        assert kwargs[1]["tool_ids"] == ["burp_organizer"]
        assert kwargs[1]["domains"] == ["web"]


class TestRun:
    def test_respects_cancellation_token(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = []
        token = CancellationToken()
        token.set()

        total = poller.run(token)
        assert total == 0


@pytest.fixture()
def enrichment() -> MagicMock:
    mock = MagicMock()
    mock.classify.return_value = NoteClassification(
        vulnerability_type="idor",
        cwe="CWE-639",
        severity="high",
    )
    return mock


@pytest.fixture()
def enriching_poller(
    fetcher: MagicMock,
    state_repo: MagicMock,
    ingest: MagicMock,
    enrichment: MagicMock,
) -> OrganizerPoller:
    return OrganizerPoller(
        fetcher=fetcher,
        state_repo=state_repo,
        ingest_service=ingest,
        project_id=1,
        note_enrichment=enrichment,
    )


class TestNormalizationAndEnrichment:
    def test_enriches_items_with_notes(
        self,
        enriching_poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
        enrichment: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [_item(1, notes="IDOR via user ID")]
        enriching_poller.poll_once()

        enrichment.classify.assert_called_once_with("IDOR via user ID")
        payload = ingest.submit_finding.call_args[0][1]
        assert payload["severity"] == "high"
        assert payload["cwe"] == ["CWE-639"]
        assert payload["finding_type"] == ["vulnerability"]
        assert payload["meta"]["vulnerability_type"] == "idor"

    def test_skips_enrichment_for_empty_notes(
        self,
        enriching_poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
        enrichment: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [_item(1, notes="")]
        enriching_poller.poll_once()

        enrichment.classify.assert_not_called()
        payload = ingest.submit_finding.call_args[0][1]
        assert payload["severity"] == "informational"
        assert payload["cwe"] == ["CWE-0"]
        assert payload["finding_type"] == ["informational"]

    def test_failed_classification_uses_placeholders(
        self,
        enriching_poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
        enrichment: MagicMock,
    ) -> None:
        enrichment.classify.return_value = None
        fetcher.fetch_items.return_value = [_item(1, notes="ambiguous")]
        enriching_poller.poll_once()

        payload = ingest.submit_finding.call_args[0][1]
        assert payload["severity"] == "informational"
        assert payload["cwe"] == ["CWE-0"]

    def test_payload_includes_normalized_http(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [
            OrganizerItem(
                id=1,
                status="New",
                request="POST /login HTTP/1.1\r\nHost: example.test\r\n",
                response="HTTP/1.1 302 Found\r\n",
                notes="",
            )
        ]
        poller.poll_once()

        meta = ingest.submit_finding.call_args[0][1]["meta"]
        assert meta["method"] == "POST"
        assert meta["url"] == "/login"
        assert meta["host"] == "example.test"
        assert meta["status_code"] == 302

    def test_no_enrichment_dependency_ingests_unclassified(
        self,
        poller: OrganizerPoller,
        fetcher: MagicMock,
        ingest: MagicMock,
    ) -> None:
        fetcher.fetch_items.return_value = [_item(1, notes="has a note")]
        poller.poll_once()

        payload = ingest.submit_finding.call_args[0][1]
        assert payload["severity"] == "informational"
        assert payload["finding_type"] == ["informational"]


class TestRepoResolution:
    def test_poll_once_sets_repo_id_from_url(self) -> None:
        """Findings are linked to the repo whose base_url matches."""
        svc = MagicMock()
        svc.base_urls = ["http://127.0.0.1:8081"]
        repo = MagicMock()
        repo.name = "webgoat"
        repo.id = 5
        repo.services = [svc]

        repo_repo = MagicMock()
        repo_repo.list_active.return_value = [repo]

        item = OrganizerItem(
            id=1,
            status="New",
            request="GET /WebGoat/login HTTP/1.1\r\nHost: 127.0.0.1:8081\r\n\r\n",
            response="<no response>",
            notes="",
        )
        fetcher = MagicMock()
        fetcher.fetch_items.return_value = [item]

        state_repo = MagicMock()
        state_repo.get_ingested_ids.return_value = set()

        ingest = MagicMock()
        ingest.create_scan_run.return_value = {"run_id": 1}
        ingest.submit_finding.return_value = {"finding_id": 10}

        poller = OrganizerPoller(
            fetcher=fetcher,
            state_repo=state_repo,
            ingest_service=ingest,
            project_id=1,
            repo_repo=repo_repo,
        )
        poller.poll_once()

        payload = ingest.submit_finding.call_args[0][1]
        assert payload["meta"]["repo_id"] == 5
        assert payload["meta"]["repo"] == "webgoat"
