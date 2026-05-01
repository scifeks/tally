"""Persistence port for the ``tool_audit_log`` table.

Concrete implementation lives at
``infrastructure.store.repositories.audit.AuditRepository``.
"""

from __future__ import annotations

from typing import Protocol


class AuditRepositoryPort(Protocol):
    def log_event(
        self,
        tool_name: str,
        arguments: dict,
        success: bool,
        error: str | None,
        duration_ms: int,
    ) -> None: ...
    def log_invocation(self, tool_name: str, arguments: dict) -> None: ...
    def count_events_since(self, tool_names: tuple[str, ...], since: str) -> int: ...
