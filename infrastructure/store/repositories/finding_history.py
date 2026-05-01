"""FindingHistoryRepository — read access for finding mutation history."""

from __future__ import annotations

import json
from typing import Any

from application.ports.finding_history_repository import (
    FindingHistoryRepositoryPort,
)
from domain.findings.entry import HistoryRow
from infrastructure.store.connection import ConnectionFactory


class FindingHistoryRepository(FindingHistoryRepositoryPort):
    """Read-only access to the finding_history table.

    Write path (inserts) is handled inside FindingRepository's update methods
    so history is always recorded in the same transaction as the mutation.
    """

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def list_for_finding(
        self,
        finding_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[HistoryRow]:
        sql = (
            "SELECT id, finding_id, timestamp, before_values, after_values,"
            " inference_context, source"
            " FROM finding_history"
            " WHERE finding_id = ?"
            " ORDER BY timestamp DESC"
            " LIMIT ? OFFSET ?"
        )
        with self._factory.connect() as conn:
            rows = conn.execute(sql, (finding_id, limit, offset)).fetchall()
        return [_row_to_dataclass(r) for r in rows]

    def count_for_finding(self, finding_id: int) -> int:
        with self._factory.connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM finding_history WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()[0]


def _row_to_dataclass(row: Any) -> HistoryRow:
    def _parse(val: str | None) -> dict[str, Any] | None:
        if val is None:
            return None
        try:
            result = json.loads(val)
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    return HistoryRow(
        id=row["id"],
        finding_id=row["finding_id"],
        timestamp=row["timestamp"],
        before_values=_parse(row["before_values"]) or {},
        after_values=_parse(row["after_values"]) or {},
        inference_context=_parse(row["inference_context"]),
        source=row["source"],
    )
