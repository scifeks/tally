"""Burp Suite scan executor with HTTP polling loop."""

from __future__ import annotations

import logging
from typing import Any

from application.ports.scan_event_sink import (
    NullScanEventSink,
    ScanEventSink,
)
from domain.locking.cancellation import CancellationToken, no_op_token
from domain.pipeline.scan_events import ToolProgress
from domain.tools.base import ToolResult
from domain.tools.burp.ports import BurpRestClientPort
from domain.tools.burp.scan_config import BurpScanConfig
from infrastructure.tools.burp.backoff import calculate_backoff
from infrastructure.tools.burp.models import BurpScanRequest
from infrastructure.tools.parsers.burp import (
    parse_burp_issue_events,
)

_log = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})


class BurpScanExecutor:
    """Polls a Burp REST API scan to completion."""

    def __init__(self, *, client: BurpRestClientPort) -> None:
        self._client = client

    def execute(
        self,
        config: BurpScanConfig,
        *,
        cancel_token: CancellationToken | None = None,
        event_sink: ScanEventSink | None = None,
        run_id: int = 0,
        project_id: int | None = None,
    ) -> ToolResult:
        token = cancel_token or no_op_token()
        sink = event_sink or NullScanEventSink()
        timestamp = ToolResult.now_iso()

        request = BurpScanRequest(
            urls=config.urls,
            name=config.task_name,
            scan_configurations=config.config_names or None,
        )
        task_id = self._client.create_scan(request)
        _log.info("Burp scan created: task_id=%s", task_id)

        all_events: list[dict[str, Any]] = []
        cursor = 0
        attempt = 0
        last_status = "initializing"

        while True:
            if token.is_set():
                _log.info("Burp scan cancelled during poll")
                break

            delay = calculate_backoff(attempt)
            if token.wait(delay):
                _log.info("Burp scan cancelled during wait")
                break

            progress = self._client.get_scan_progress(task_id, after=cursor)
            last_status = progress.status

            new_events = progress.issue_events
            if new_events:
                all_events.extend(new_events)
                cursor += len(new_events)

            pct = progress.metrics.get("crawl_and_audit_progress", 0)
            sink.emit(
                ToolProgress(
                    run_id=run_id,
                    project_id=project_id,
                    segment="web",
                    tool="burp",
                    message=f"Burp scan {last_status}",
                    status=last_status,
                    findings_count=len(all_events),
                    progress_pct=int(pct),
                )
            )

            if last_status in _TERMINAL_STATUSES:
                break

            if config.timeout is not None and self._elapsed_exceeds(
                progress.metrics, config.timeout
            ):
                _log.warning(
                    "Burp scan timed out after %ds",
                    config.timeout,
                )
                break

            attempt += 1

        parsed = parse_burp_issue_events(all_events)
        finding_count = parsed["summary"]["total_findings"]
        success = last_status == "succeeded" or (token.is_set() and finding_count > 0)

        return ToolResult(
            tool_name="burp",
            success=success,
            output=f"Burp scan {last_status}: {finding_count} findings",
            parsed_data=parsed,
            output_files={},
            timestamp=timestamp,
            duration_seconds=0.0,
            finding_count=finding_count,
        )

    @staticmethod
    def _elapsed_exceeds(metrics: dict[str, Any], timeout: int) -> bool:
        elapsed = metrics.get("total_elapsed_time", 0)
        return int(elapsed) >= timeout
