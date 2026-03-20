"""AuditRepository — tool_audit_log write and read operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.store.connection import ConnectionFactory


class AuditRepository:
    """Manages the tool_audit_log table."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def log_event(
        self,
        tool_name: str,
        arguments: dict,
        success: bool,
        error: str | None,
        duration_ms: int,
    ) -> None:
        """Insert one row into tool_audit_log."""
        from datetime import UTC, datetime

        called_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            conn.execute(
                "INSERT INTO tool_audit_log"
                " (tool_name, arguments, success, error, duration_ms, called_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tool_name,
                    json.dumps(arguments),
                    1 if success else 0,
                    error,
                    duration_ms,
                    called_at,
                ),
            )

    def count_events_since(self, tool_names: tuple[str, ...], since: str) -> int:
        """Count audit log entries for tool_names recorded at or after since."""
        placeholders = ",".join("?" * len(tool_names))
        with self._factory.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM tool_audit_log"
                f" WHERE tool_name IN ({placeholders}) AND called_at >= ?",
                (*tool_names, since),
            ).fetchone()
        return row[0] if row else 0
