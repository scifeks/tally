"""Tests for BurpScanExecutor polling loop."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.ports.scan_event_sink import NullScanEventSink
from domain.locking.cancellation import CancellationToken
from domain.tools.burp.scan_config import BurpScanConfig
from infrastructure.tools.burp.models import (
    BurpScanProgress,
    BurpScanRequest,
)
from infrastructure.tools.burp.scan_executor import (
    BurpScanExecutor,
)


def _make_executor(
    client: MagicMock | None = None,
) -> tuple[BurpScanExecutor, MagicMock]:
    mock_client = client or MagicMock()
    executor = BurpScanExecutor(client=mock_client)
    return executor, mock_client


def _progress(
    status: str = "crawling",
    metrics: dict | None = None,
    issue_events: list | None = None,
) -> BurpScanProgress:
    return BurpScanProgress(
        status=status,
        metrics=metrics or {},
        issue_events=issue_events or [],
    )


class TestBurpScanExecutor:
    def test_creates_scan_with_urls(self) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "42"
        client.get_scan_progress.return_value = _progress(status="succeeded")
        config = BurpScanConfig(urls=["https://example.com"])

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            executor.execute(config, event_sink=NullScanEventSink())

        client.create_scan.assert_called_once()
        req = client.create_scan.call_args[0][0]
        assert isinstance(req, BurpScanRequest)
        assert req.urls == ["https://example.com"]

    def test_cursor_advances_across_polls(self) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "1"
        client.get_scan_progress.side_effect = [
            _progress(
                issue_events=[
                    {"type": "issue_found", "issue": {"name": "A"}},
                    {"type": "issue_found", "issue": {"name": "B"}},
                ]
            ),
            _progress(
                issue_events=[
                    {"type": "issue_found", "issue": {"name": "C"}},
                ]
            ),
            _progress(status="succeeded"),
        ]
        config = BurpScanConfig(urls=["https://example.com"])

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            result = executor.execute(config, event_sink=NullScanEventSink())

        after_values = [
            c.kwargs["after"] for c in client.get_scan_progress.call_args_list
        ]
        assert after_values == [0, 2, 3]
        assert result.finding_count == 3

    def test_cancel_token_stops_polling(self) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "1"
        token = CancellationToken()

        call_count = 0
        original_progress = _progress(
            issue_events=[{"type": "issue_found", "issue": {"name": "X"}}]
        )

        def cancel_on_second_poll(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                token.set()
            return original_progress

        client.get_scan_progress.side_effect = cancel_on_second_poll
        config = BurpScanConfig(urls=["https://example.com"])

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            result = executor.execute(
                config,
                cancel_token=token,
                event_sink=NullScanEventSink(),
            )

        assert call_count == 2
        assert result.finding_count > 0

    @pytest.mark.parametrize(
        "terminal_status",
        ["succeeded", "failed"],
        ids=["succeeded", "failed"],
    )
    def test_terminal_status_ends_polling(self, terminal_status: str) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "1"
        client.get_scan_progress.return_value = _progress(status=terminal_status)
        config = BurpScanConfig(urls=["https://example.com"])

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            result = executor.execute(config, event_sink=NullScanEventSink())

        client.get_scan_progress.assert_called_once()
        assert result.success == (terminal_status == "succeeded")

    def test_accumulates_events_across_polls(self) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "1"
        batch_1 = [
            {"type": "issue_found", "issue": {"name": "A"}},
        ]
        batch_2 = [
            {"type": "issue_found", "issue": {"name": "B"}},
            {"type": "issue_found", "issue": {"name": "C"}},
        ]
        client.get_scan_progress.side_effect = [
            _progress(issue_events=batch_1),
            _progress(issue_events=batch_2),
            _progress(status="succeeded"),
        ]
        config = BurpScanConfig(urls=["https://example.com"])

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            result = executor.execute(config, event_sink=NullScanEventSink())

        assert result.parsed_data is not None
        findings = result.parsed_data["findings"]
        names = [f["name"] for f in findings]
        assert names == ["A", "B", "C"]

    def test_emits_progress_on_each_poll(self) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "1"
        client.get_scan_progress.side_effect = [
            _progress(
                status="crawling",
                metrics={"crawl_and_audit_progress": 30},
            ),
            _progress(
                status="auditing",
                metrics={"crawl_and_audit_progress": 70},
            ),
            _progress(
                status="succeeded",
                metrics={"crawl_and_audit_progress": 100},
            ),
        ]
        config = BurpScanConfig(urls=["https://example.com"])
        sink = MagicMock()

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            executor.execute(config, event_sink=sink)

        assert sink.emit.call_count == 3
        statuses = [c.args[0].status for c in sink.emit.call_args_list]
        assert statuses == [
            "crawling",
            "auditing",
            "succeeded",
        ]
        pcts = [c.args[0].progress_pct for c in sink.emit.call_args_list]
        assert pcts == [30, 70, 100]

    def test_timeout_stops_polling(self) -> None:
        executor, client = _make_executor()
        client.create_scan.return_value = "1"
        client.get_scan_progress.return_value = _progress(
            status="auditing",
            metrics={"total_elapsed_time": 600},
        )
        config = BurpScanConfig(urls=["https://example.com"], timeout=300)

        with patch(
            "infrastructure.tools.burp.scan_executor.calculate_backoff",
            return_value=0.0,
        ):
            result = executor.execute(config, event_sink=NullScanEventSink())

        client.get_scan_progress.assert_called_once()
        assert not result.success
