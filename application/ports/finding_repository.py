"""Persistence port for the ``findings`` table.

Concrete implementation lives at
``infrastructure.store.repositories.findings.FindingRepository``.

Read methods on this port currently return ``dict[str, Any]`` to match
the existing repository contract. This is a transitional shape: a
follow-up slice will introduce a ``Finding`` domain dataclass and
move JSON parsing and severity-rank translation out of the web and
MCP adapters into an application service. Until then, callers
continue to consume raw row dicts.
"""

from __future__ import annotations

from typing import Any, Protocol


class FindingRepositoryPort(Protocol):
    def insert_findings(self, run_id: int, findings: list[dict]) -> None: ...
    def delete_findings(self, tools: list[str] | None = None) -> None: ...
    def delete_findings_by_tool_name(self, tools: list[str]) -> None: ...
    def get_tool_meta_keys(
        self, tool_name: str, sample: int = 200
    ) -> tuple[int, set[str]]: ...
    def get_finding(self, finding_id: int) -> dict | None: ...
    def get_findings(
        self,
        tools: list[str] | None = None,
        domain: str | None = None,
        status: str | None = None,
        segments: list[str] | None = None,
        require_file: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict]: ...
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
    def get_reportable_findings(self) -> list[dict]: ...
    def get_findings_marked_for_report(self) -> list[dict]: ...
    def get_all_findings(self) -> list[dict]: ...
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
    def search_raw(self, filters: dict) -> list[dict]: ...
    def search_count(self, filters: dict) -> int: ...
    def count_aggregates(self) -> dict: ...
    def distinct_facet_values(self) -> dict: ...
    def filter_options(self, filters: dict) -> dict: ...
