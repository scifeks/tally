"""Unit tests for orchestrator HTTP-transport routing."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from domain.tools.base import ToolResult
from domain.tools.scan_types.models import ScanSummary

if TYPE_CHECKING:
    from application.tools.orchestrator import ScanOrchestrator


def _burp_result(finding_count: int = 3) -> ToolResult:
    return ToolResult(
        tool_name="burp",
        success=True,
        output="Burp scan succeeded",
        parsed_data={
            "findings": [],
            "summary": {"total_findings": finding_count},
        },
        output_files={},
        timestamp="2026-08-25T00:00:00",
        duration_seconds=60.0,
        finding_count=finding_count,
    )


def _make_orchestrator(*, http_runner: MagicMock | None = None) -> ScanOrchestrator:
    from application.tools.orchestrator import ScanOrchestrator

    registry = MagicMock()
    registry.list_tool_names.return_value = ["burp"]
    executor = MagicMock()
    executor.base_path = "/tmp/test"
    event_bus = MagicMock()
    prompt = MagicMock()
    prompt.confirm.return_value = True

    with patch("application.tools.orchestrator._build_tool_execution_config"):
        with patch("core.config.manager.ConfigManager"):
            orch = ScanOrchestrator(
                project="test",
                tool_registry=registry,
                tool_executor=executor,
                event_bus=event_bus,
                prompt=prompt,
                http_runner=http_runner,
                project_id=1,
                run_id=10,
            )
    return orch


class TestOrchestratorBurpRouting:
    def test_run_burp_scan_dispatches_to_burp_scan_type(
        self,
    ) -> None:
        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()
        orch = _make_orchestrator(http_runner=runner)

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=3,
        ):
            summary = orch.run_burp_scan(urls=["https://target.example.com"])

        runner.execute_burp.assert_called_once()
        assert isinstance(summary, ScanSummary)

    def test_run_burp_scan_passes_timeout(self) -> None:
        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()
        orch = _make_orchestrator(http_runner=runner)

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=0,
        ):
            orch.run_burp_scan(
                urls=["https://target.example.com"],
                timeout=300,
            )

        scan_config = runner.execute_burp.call_args.args[0]
        assert scan_config.timeout == 300

    def test_run_burp_scan_uses_cancel_token(
        self,
    ) -> None:
        runner = MagicMock()
        runner.execute_burp.return_value = _burp_result()
        orch = _make_orchestrator(http_runner=runner)

        with patch(
            "application.tools.scan_types.burp.dispatch_and_count_ingested",
            return_value=0,
        ):
            orch.run_burp_scan(urls=["https://target.example.com"])

        call_kwargs = runner.execute_burp.call_args.kwargs
        assert call_kwargs["cancel_token"] is not None


class TestHttpTransportGuard:
    """HTTP-transport tools return None from
    execute_tool_passes so full scans skip them."""

    def test_http_tool_returns_none(self) -> None:
        from application.tools.scan_types.execution import execute_tool_passes

        tool = MagicMock()
        tool.transport = __import__(
            "domain.tools.interface",
            fromlist=["TransportType"],
        ).TransportType.HTTP

        result = execute_tool_passes(
            tool,
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        assert result is None

    def test_cli_tool_proceeds_normally(self) -> None:
        from application.tools.scan_types.execution import execute_tool_passes
        from domain.tools.interface import TransportType

        tool = MagicMock()
        tool.transport = TransportType.CLI
        config = MagicMock()
        config.prompt.confirm.return_value = False

        result = execute_tool_passes(tool, MagicMock(), config, MagicMock())
        assert result is None
