"""BurpScanType: dispatches a Burp crawl-and-audit scan."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING

from application.tools.scan_types.base import ScanType
from application.tools.scan_types.execution import (
    dispatch_and_count_ingested,
)
from application.tools.scan_types.models import ScanTypeConfig
from domain.locking.cancellation import CancellationToken
from domain.pipeline import scan_events as se
from domain.pipeline.events import ToolCompleted
from domain.tools.burp.scan_config import BurpScanConfig
from domain.tools.display import ToolDisplayRow
from domain.tools.scan_types.models import ScanSummary
from domain.tools.scan_types.resources import (
    IExecutionResources,
)

if TYPE_CHECKING:
    from infrastructure.tools.http_runner import HttpToolRunner

_log = logging.getLogger(__name__)


class BurpScanType(ScanType):
    """Run a Burp crawl-and-audit scan via the REST API."""

    def __init__(
        self,
        *,
        http_runner: HttpToolRunner,
        urls: list[str],
        cancel_token: CancellationToken | None = None,
        timeout: int | None = None,
    ) -> None:
        self._http_runner = http_runner
        self._urls = urls
        self._cancel_token = cancel_token
        self._timeout = timeout

    def execute(
        self,
        config: ScanTypeConfig,
        resources: IExecutionResources,
    ) -> ScanSummary:
        start = perf_counter()
        run_id = config.run_id or 0
        project_id = config.project_id

        resources.display.print_scan_header(f"Burp Scan: {config.project_name}")

        resources.event_sink.emit(
            se.ToolStarted(
                run_id=run_id,
                project_id=project_id,
                segment="web",
                repo="",
                tool="burp",
                message="burp scan started",
            )
        )

        scan_config = BurpScanConfig(urls=self._urls, timeout=self._timeout)
        result = self._http_runner.execute_burp(
            scan_config,
            cancel_token=self._cancel_token,
            event_sink=resources.event_sink,
            run_id=run_id,
            project_id=project_id,
        )

        duration = round(perf_counter() - start, 1)
        findings = result.finding_count
        tools_run = 0
        tools_failed = 0
        ingested = 0

        if result.success:
            tools_run = 1
            resources.display.print_tool_line(
                ToolDisplayRow(
                    "burp",
                    True,
                    False,
                    findings,
                    duration,
                )
            )
            resources.event_sink.emit(
                se.ToolCompleted(
                    run_id=run_id,
                    project_id=project_id,
                    segment="web",
                    repo="",
                    tool="burp",
                    message="burp scan complete",
                    findings_count=findings,
                    duration=duration,
                    exit_code=0,
                )
            )
            ingested = dispatch_and_count_ingested(
                resources.event_bus,
                ToolCompleted(
                    result,
                    "",
                    config.run_id,
                    config.project_name,
                    config.base_path,
                    repo="",
                ),
            )
        else:
            tools_failed = 1
            resources.display.print_tool_line(
                ToolDisplayRow("burp", False, False, 0, duration)
            )
            resources.event_sink.emit(
                se.ToolFailed(
                    run_id=run_id,
                    project_id=project_id,
                    segment="web",
                    repo="",
                    tool="burp",
                    message="burp scan failed",
                    exit_code=1,
                    duration=duration,
                )
            )

        summary = ScanSummary(
            total_tools_run=tools_run,
            total_tools_skipped=0,
            total_tools_failed=tools_failed,
            results=[result],
            duration_seconds=duration,
            findings_ingested=ingested,
            findings_by_tool=({"burp": ingested} if ingested else {}),
        )
        resources.display.print_final_line(
            run=summary.total_tools_run,
            failed=summary.total_tools_failed,
            skipped=0,
            ingested=summary.findings_ingested,
            duration=summary.duration_seconds,
        )
        return summary
