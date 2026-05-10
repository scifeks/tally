"""Port for human-readable tool execution progress."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressReporter(Protocol):
    """Single-method port for status lines emitted by the executor.

    Adapters decide whether and how to surface the message. The core
    does not know if a human is watching.
    """

    def report(self, message: str) -> None: ...


class NullProgressReporter:
    """Default no-op reporter. Drops every message."""

    def report(self, message: str) -> None:
        del message
        return None
