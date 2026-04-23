"""FindingAnalystService — application-layer facade for analyst-driven operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from infrastructure.store.repositories.findings import FindingRepository


class FindingAnalystService:
    def __init__(self, repo: FindingRepository) -> None:
        self._repo = repo

    def get_finding(self, finding_id: int) -> dict | None:
        return self._repo.get_finding(finding_id)

    def get_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        limit: int = 10_000,
    ) -> list[dict]:
        return self._repo.get_findings(
            tools=tools,
            domain=domain,
            status=status,
            segments=segments,
            limit=limit,
        )

    def update_fields(self, finding_id: int, fields: dict[str, Any]) -> bool:
        return self._repo.update_analyst_fields(finding_id, fields)

    def bulk_update_fields(self, ids: list[int], fields: dict[str, Any]) -> int:
        return self._repo.batch_update_analyst_fields(ids, fields)
