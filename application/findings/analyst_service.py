"""FindingAnalystService — application-layer facade for analyst-driven operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from application.locking import FindingsBusy, LockRegistry, get_registry

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from domain.findings.entry import Finding


@dataclass
class BulkUpdateResult:
    """Result of a bulk finding update with per-id outcome tracking."""

    updated: list[int] = field(default_factory=list)
    skipped_locked: list[int] = field(default_factory=list)
    not_found: list[int] = field(default_factory=list)
    skip_reasons: dict[int, str] = field(default_factory=dict)


class FindingAnalystService:
    def __init__(
        self,
        repo: FindingRepositoryPort,
        registry: LockRegistry | None = None,
    ) -> None:
        self._repo = repo
        self._registry = registry if registry is not None else get_registry()

    def get_finding(self, finding_id: int) -> Finding | None:
        return self._repo.get_finding(finding_id)

    def get_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        limit: int = 10_000,
        offset: int = 0,
    ) -> list[Finding]:
        return self._repo.get_findings(
            tools=tools,
            domain=domain,
            status=status,
            segments=segments,
            limit=limit,
            offset=offset,
        )

    def count_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
    ) -> int:
        return self._repo.count_findings(
            tools=tools,
            domain=domain,
            status=status,
            segments=segments,
        )

    def update_fields(
        self,
        finding_id: int,
        fields: dict[str, Any],
        *,
        holder_token: str,
    ) -> bool:
        """Acquire the finding lock, write, release. Raises FindingsBusy if held."""
        with self._registry.findings([finding_id], holder_token):
            return self._repo.update_analyst_fields(finding_id, fields, source="web_ui")

    def update_fields_under_held_lock(
        self,
        finding_id: int,
        fields: dict[str, Any],
        *,
        holder_token: str,
    ) -> bool:
        """Write without acquiring the lock. Asserts *holder_token* already holds.

        For callers (triage MCP) that pre-acquired the batch. Raises
        HolderMismatch if the finding is held by a different token.
        """
        self._registry.assert_held_by(finding_id, holder_token)
        return self._repo.update_analyst_fields(finding_id, fields, source="web_ui")

    def bulk_update_fields(
        self,
        ids: list[int],
        fields: dict[str, Any],
        *,
        holder_token: str,
    ) -> BulkUpdateResult:
        """Per-id acquire, skip locked rows, update the rest.

        Returns a BulkUpdateResult with three disjoint id buckets:
        updated, skipped_locked, not_found.
        """
        result = BulkUpdateResult()
        for finding_id in ids:
            if self._repo.get_finding(finding_id) is None:
                result.not_found.append(finding_id)
                continue
            try:
                with self._registry.findings([finding_id], holder_token):
                    self._repo.update_analyst_fields(
                        finding_id, fields, source="web_ui"
                    )
                result.updated.append(finding_id)
            except FindingsBusy:
                result.skipped_locked.append(finding_id)
                result.skip_reasons[finding_id] = "FINDING_LOCKED"
        return result

    def bulk_update_fields_under_held_lock(
        self,
        ids: list[int],
        fields: dict[str, Any],
        *,
        holder_token: str,
    ) -> BulkUpdateResult:
        """Pre-held bulk variant. Asserts *holder_token* holds each id.

        Raises HolderMismatch (not skipped) — a mismatch is always a bug.
        """
        result = BulkUpdateResult()
        for finding_id in ids:
            if self._repo.get_finding(finding_id) is None:
                result.not_found.append(finding_id)
                continue
            self._registry.assert_held_by(finding_id, holder_token)
            self._repo.update_analyst_fields(finding_id, fields, source="web_ui")
            result.updated.append(finding_id)
        return result

    def search_raw(self, filters: dict) -> list[Finding]:
        return self._repo.search_raw(filters)

    def search_count(self, filters: dict) -> int:
        return self._repo.search_count(filters)

    def count_aggregates(self) -> dict:
        return self._repo.count_aggregates()

    def distinct_facet_values(self) -> dict:
        return self._repo.distinct_facet_values()

    def filter_options(self, filters: dict) -> dict:
        return self._repo.filter_options(filters)
