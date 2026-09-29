"""HTTP tool runner: delegates to tool-specific scan executors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.ports.scan_event_sink import (
    NullScanEventSink,
    ScanEventSink,
)
from domain.locking.cancellation import CancellationToken
from domain.tools.base import ToolResult
from domain.tools.burp.scan_config import BurpScanConfig
from infrastructure.tools.burp.scan_executor import (
    BurpScanExecutor,
)

if TYPE_CHECKING:
    from domain.tools.burp.ports import BurpRestClientPort


class HttpToolRunner:
    """Adapter for HTTP polling-based tool execution.

    Wraps tool-specific executors behind a common entry point.
    """

    def __init__(self, *, burp_client: BurpRestClientPort | None = None) -> None:
        self._burp_executor: BurpScanExecutor | None = None
        if burp_client is not None:
            self._burp_executor = BurpScanExecutor(client=burp_client)

    def execute_burp(
        self,
        config: BurpScanConfig,
        *,
        cancel_token: CancellationToken | None = None,
        event_sink: ScanEventSink | None = None,
        run_id: int = 0,
        project_id: int | None = None,
    ) -> ToolResult:
        if self._burp_executor is None:
            return ToolResult(
                tool_name="burp",
                success=False,
                output="Burp client not configured",
                parsed_data=None,
                output_files={},
                timestamp=ToolResult.now_iso(),
                duration_seconds=0.0,
            )
        return self._burp_executor.execute(
            config,
            cancel_token=cancel_token,
            event_sink=event_sink or NullScanEventSink(),
            run_id=run_id,
            project_id=project_id,
        )
