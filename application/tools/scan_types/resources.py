"""ExecutionResources: bundles application-layer services for scan type strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from application.ports.scan_event_sink import NullScanEventSink, ScanEventSink

if TYPE_CHECKING:
    from application.tools.executor import ToolExecutor
    from application.tools.factory import ToolWrapperFactory
    from application.tools.registry import ToolRegistry
    from domain.pipeline.events import EventBus
    from domain.tools.display import DisplayProtocol
    from infrastructure.tools.http_runner import HttpToolRunner


@dataclass
class ExecutionResources:
    executor: ToolExecutor
    registry: ToolRegistry
    factory: ToolWrapperFactory
    event_bus: EventBus
    display: DisplayProtocol
    event_sink: ScanEventSink = field(default_factory=NullScanEventSink)
    http_runner: HttpToolRunner | None = None
