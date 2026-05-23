"""Persistence port for the findings table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from domain.findings.entry import Finding
    from domain.findings.normalization import NormalizedFinding


class FindingRepositoryPort(Protocol):
    def insert_findings(
        self, run_id: int, findings: list[NormalizedFinding]
    ) -> None: ...
    def delete_findings(self, tools: list[str] | None = None) -> None: ...
    def delete_findings_by_tool_name(self, tools: list[str]) -> None: ...
    def get_tool_meta_keys(
        self, tool_name: str, sample: int = 200
    ) -> tuple[int, set[str]]: ...
    def get_finding(self, finding_id: int) -> Finding | None: ...
    def get_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Finding]: ...
    def count_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
    ) -> int: ...
    def update_finding(
        self,
        finding_id: int,
        severity_rank: int,
        confidence: str,
        finding_type_json: str,
        triage_meta: dict,
        strategy: str,
        *,
        triaged_by: str = "claudecode",
        source: str = "auto_triage",
    ) -> bool: ...
    def get_reportable_findings(self) -> list[Finding]: ...
    def get_findings_marked_for_report(self) -> list[Finding]: ...
    def get_all_findings(self) -> list[Finding]: ...
    def get_findings_by_run_id(self, run_id: int) -> list[Finding]: ...
    def get_all_findings_deserialized(self) -> list[dict]: ...
    def update_analyst_fields(
        self,
        finding_id: int,
        columns: dict[str, Any],
        meta: dict[str, Any],
        *,
        source: str = "web_ui",
    ) -> bool: ...
    def batch_update_analyst_fields(
        self,
        ids: list[int],
        fields: dict[str, Any],
    ) -> int: ...
    def reset_tal_ids(self) -> None: ...
    def bulk_update_tal_ids(self, pairs: list[tuple[str, int]]) -> None: ...
    def get_ids_by_fingerprints(
        self, fingerprints: list[str], run_id: int | None = None
    ) -> list[int]: ...
    def get_by_ids(self, ids: list[int]) -> list[dict]: ...
    def update_enrichment_fields(
        self,
        finding_id: int,
        columns: dict[str, Any],
        meta: dict[str, Any],
        *,
        source: str = "llm_inference",
    ) -> None: ...
    def search(self, filters: dict) -> list[dict]: ...
    def search_raw(self, filters: dict) -> list[Finding]: ...
    def search_count(self, filters: dict) -> int: ...
    def count_aggregates(self) -> dict: ...
    def distinct_facet_values(self) -> dict: ...
    def filter_options(self, filters: dict) -> dict: ...
    def insert_manual_finding(
        self,
        columns: dict[str, Any],
        meta: dict[str, Any],
        fingerprint: str,
    ) -> int: ...
    def delete_finding_by_id(self, finding_id: int) -> None: ...
