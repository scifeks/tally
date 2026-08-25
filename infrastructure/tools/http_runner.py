"""HTTP tool runner stub.

Reserves the extension point for HTTP-based tool execution.
Concrete implementation is pending.
"""

from __future__ import annotations

from application.ports.tool_runner import ToolRunOutput


class HttpToolRunner:
    """Placeholder for HTTP polling-based tool execution.

    Sends HTTP requests, polls with exponential backoff, collects
    incremental results, and respects cancellation.
    """

    def execute(self) -> ToolRunOutput:
        raise NotImplementedError("HTTP tool execution is not yet implemented")
