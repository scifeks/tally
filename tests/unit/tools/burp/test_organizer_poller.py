"""Unit tests for OrganizerPoller."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.tools.burp.organizer_poller import (  # noqa: E402
    OrganizerPoller,
)
from domain.locking.cancellation import (  # noqa: E402
    CancellationToken,
)
from domain.tools.burp.mcp_ports import (  # noqa: E402
    OrganizerItem,
)


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
