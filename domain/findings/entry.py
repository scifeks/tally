"""Domain entries for the findings surface.

``HistoryRow`` is the row-shaped value object returned by
``FindingHistoryRepositoryPort.list_for_finding``. It lives in
``domain/`` so port signatures depend on a domain type rather than an
infrastructure dataclass (Rule 7). Field-equivalent to the row persisted
in ``finding_history``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HistoryRow:
    id: int
    finding_id: int
    timestamp: str
    before_values: dict[str, Any]
    after_values: dict[str, Any]
    inference_context: dict[str, Any] | None
    source: str
