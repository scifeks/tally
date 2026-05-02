"""Persistence port for the ``reports`` table.

Concrete implementation lives at
``infrastructure.store.repositories.reports.ReportRepository``. Read
methods return ``domain.reports.entry.ReportRow`` so the port boundary
stays free of infrastructure dataclasses.

No application-layer caller imports ``ReportRepository`` today: every
consumer lives in ``web/``. The port is introduced here to satisfy the
"one Protocol port per repository" plan and to position A7, where the
report runner logic moves into an application service that will
consume this port directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.reports.entry import ReportRow


class ReportRepositoryPort(Protocol):
    def create(
        self,
        *,
        project_id: int,
        scan_run_id: int | None,
        format: str,
        filename: str,
        filepath: str,
        status: str = "queued",
        retention_tier: str = "auto",
    ) -> int: ...
    def set_status(self, report_id: int, status: str) -> None: ...
    def set_started_at(self, report_id: int, when: str | None = None) -> None: ...
    def set_finished_at(self, report_id: int, when: str | None = None) -> None: ...
    def set_file_size(self, report_id: int, size: int) -> None: ...
    def set_error(self, report_id: int, message: str) -> None: ...
    def set_pinned(self, report_id: int, pinned: bool) -> None: ...
    def delete(self, report_id: int) -> None: ...
    def get(self, report_id: int) -> ReportRow | None: ...
    def list_for_project(
        self,
        project_id: int,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[ReportRow], int]: ...
    def latest_for_project(self, project_id: int) -> ReportRow | None: ...
    def select_for_retention(
        self,
        project_id: int,
        *,
        keep: int,
    ) -> list[ReportRow]: ...
