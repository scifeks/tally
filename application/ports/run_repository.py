"""Persistence port for the scan_runs and run_tools tables.

Read methods return domain row dataclasses. The port boundary stays free
of infrastructure dataclasses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from domain.scans.entry import ScanRunRow, ToolRunRow


class RunRepositoryPort(Protocol):
    def create_run(self, args: dict) -> int: ...
    def add_run_tools(self, run_id: int, tools: list[dict]) -> None: ...
    def create(
        self,
        *,
        project_id: int,
        repo_ids: list[str],
        tool_ids: list[str],
        domains: list[str],
        skip_enrichment: bool,
        args: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> int: ...
    def set_status(self, run_id: int, status: str) -> None: ...
    def set_started_at(self, run_id: int, when: str | None = None) -> None: ...
    def set_finished_at(self, run_id: int, when: str | None = None) -> None: ...
    def set_findings_count(self, run_id: int, count: int) -> None: ...
    def mark_stale_runs_failed(self) -> int: ...
    def get(self, run_id: int) -> ScanRunRow | None: ...
    def latest_run_id(self) -> int | None: ...
    def list_for_project(
        self,
        project_id: int,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ScanRunRow], int]: ...
    def get_with_tool_runs(
        self, run_id: int
    ) -> tuple[ScanRunRow, list[ToolRunRow]] | None: ...
    def add_tool_run(
        self,
        *,
        run_id: int,
        tool: str,
        repo: str | None = None,
        domain: str | None = None,
        status: str = "queued",
    ) -> int: ...
    def update_tool_run(
        self,
        tool_run_id: int,
        *,
        status: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        exit_code: int | None = None,
        skip_reason: str | None = None,
        findings_count: int | None = None,
        enriched_count: int | None = None,
        total_to_enrich: int | None = None,
    ) -> None: ...
