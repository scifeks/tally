"""Persistence port for the ``findings`` table.

Concrete implementation lives at
``infrastructure.store.repositories.findings.FindingRepository``.

Read methods return parsed ``domain.findings.entry.Finding`` instances
(JSON columns deserialised, severity translated from integer rank to
lowercase label). The Chroma-compatible methods ``search``,
``get_by_ids``, and ``get_all_findings_deserialized`` continue to
return dicts shaped for the vector store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from domain.findings.entry import Finding


class FindingRepositoryPort(Protocol):
    def insert_findings(self, run_id: int, findings: list[dict]) -> None: ...
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
        confidence: str,
        finding_type: str,
        severity: str,
        reasoning: str,
        remediation: str,
        attack_vector: str | None,
        call_stack: str | None,
        strategy: str,
        *,
        source: str = "auto_triage",
    ) -> bool: ...
    def get_reportable_findings(self) -> list[Finding]: ...
    def get_findings_marked_for_report(self) -> list[Finding]: ...
    def get_all_findings(self) -> list[Finding]: ...
    def get_all_findings_deserialized(self) -> list[dict]: ...
    def update_analyst_fields(
        self,
        finding_id: int,
        fields: dict[str, Any],
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
        fields: dict,
        *,
        source: str = "llm_inference",
    ) -> None: ...
    def search(self, filters: dict) -> list[dict]: ...
    def search_raw(self, filters: dict) -> list[Finding]: ...
    def search_count(self, filters: dict) -> int: ...
    def count_aggregates(self) -> dict: ...
    def distinct_facet_values(self) -> dict: ...
    def filter_options(self, filters: dict) -> dict: ...
