"""Persistence port for the finding_history table (read-side)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.findings.entry import HistoryRow


class FindingHistoryRepositoryPort(Protocol):
    def list_for_finding(
        self,
        finding_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[HistoryRow]: ...
    def count_for_finding(self, finding_id: int) -> int: ...
