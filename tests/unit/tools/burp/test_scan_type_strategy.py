"""Unit tests for BurpScanType strategy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from domain.tools.base import ToolResult
from domain.tools.scan_types.models import ScanSummary


def _mock_config() -> MagicMock:
    config = MagicMock()
    config.project_name = "test-project"
    config.run_id = 42
    config.project_id = 1
    config.remaining_peers = 0
    config.base_path = "/tmp/test"
    return config


def _mock_resources() -> MagicMock:
    resources = MagicMock()
    resources.display = MagicMock()
    resources.event_sink = MagicMock()
    resources.event_bus = MagicMock()
    return resources


def _burp_result(*, success: bool = True, finding_count: int = 3) -> ToolResult:
    return ToolResult(
        tool_name="burp",
        success=success,
        output=f"Burp scan succeeded: {finding_count} findings",
        parsed_data={
            "findings": [{"name": f"f{i}"} for i in range(finding_count)],
            "summary": {"total_findings": finding_count},
        },
        output_files={},
        timestamp="2026-08-25T00:00:00",
        duration_seconds=120.0,
        finding_count=finding_count,
    )


class TestBurpScanType:
    def test_dispatches_executor_with_urls(self) -> None:
        from application.tools.scan_types.burp import (
            BurpScanType,
        )

        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()

        strategy = BurpScanType(
            http_runner=runner,
            urls=["https://target.example.com"],
            cancel_token=None,
        )

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=3,
        ):
            strategy.execute(_mock_config(), _mock_resources())

        runner.execute_burp.assert_called_once()
        call_args = runner.execute_burp.call_args
        scan_config = call_args.args[0]
        assert scan_config.urls == ["https://target.example.com"]

    def test_returns_scan_summary(self) -> None:
        from application.tools.scan_types.burp import (
            BurpScanType,
        )

        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result(finding_count=5)

        strategy = BurpScanType(
            http_runner=runner,
            urls=["https://app.example.com"],
            cancel_token=None,
        )

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=5,
        ):
            summary = strategy.execute(_mock_config(), _mock_resources())

        assert isinstance(summary, ScanSummary)
        assert summary.total_tools_run == 1
        assert summary.findings_ingested == 5

    def test_passes_cancel_token(self) -> None:
        from application.tools.scan_types.burp import (
            BurpScanType,
        )

        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()
        token = MagicMock()

        strategy = BurpScanType(
            http_runner=runner,
            urls=["https://target.example.com"],
            cancel_token=token,
        )

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=3,
        ):
            strategy.execute(_mock_config(), _mock_resources())

        call_kwargs = runner.execute_burp.call_args.kwargs
        assert call_kwargs["cancel_token"] is token

    def test_passes_timeout(self) -> None:
        from application.tools.scan_types.burp import (
            BurpScanType,
        )

        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()

        strategy = BurpScanType(
            http_runner=runner,
            urls=["https://target.example.com"],
            cancel_token=None,
            timeout=600,
        )

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=3,
        ):
            strategy.execute(_mock_config(), _mock_resources())

        scan_config = runner.execute_burp.call_args.args[0]
        assert scan_config.timeout == 600

    def test_failed_scan_counts_as_failed(self) -> None:
        from application.tools.scan_types.burp import (
            BurpScanType,
        )

        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result(success=False, finding_count=0)

        strategy = BurpScanType(
            http_runner=runner,
            urls=["https://target.example.com"],
            cancel_token=None,
        )

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=0,
        ):
            summary = strategy.execute(_mock_config(), _mock_resources())

        assert summary.total_tools_failed == 1
        assert summary.total_tools_run == 0

    def test_dispatches_tool_completed_event(
        self,
    ) -> None:
        from application.tools.scan_types.burp import (
            BurpScanType,
        )

        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()
        resources = _mock_resources()

        strategy = BurpScanType(
            http_runner=runner,
            urls=["https://target.example.com"],
            cancel_token=None,
        )

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=3,
        ) as mock_dispatch:
            strategy.execute(_mock_config(), resources)

        mock_dispatch.assert_called_once()
