"""Persistence port for saved scan definitions and related data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.saved_scans.entry import (
        SavedScanHydrated,
        SavedScanListItem,
        SavedScanReference,
    )


class SavedScanNameConflict(Exception):
    """Raised when ``name`` collides with an existing row."""

    def __init__(self, name: str) -> None:
        super().__init__(f"saved scan {name!r} already exists")
        self.name = name


class SavedScansRepositoryPort(Protocol):
    def list_for_project(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SavedScanListItem], int]: ...
    def get_hydrated(self, saved_scan_id: int) -> SavedScanHydrated | None: ...
    def list_arg_profile_ids(self, saved_scan_id: int) -> list[int]: ...
    def find_referencing_arg_profile(
        self, arg_profile_id: int
    ) -> list[SavedScanReference]: ...
    def insert(
        self,
        *,
        name: str,
        skip_enrichment: bool,
        repo_ids: list[int],
        tool_names: list[str],
        skip_tool_names: list[str],
        segments: list[str],
        arg_profile_ids: list[int],
    ) -> int: ...
    def replace(
        self,
        saved_scan_id: int,
        *,
        name: str,
        skip_enrichment: bool,
        repo_ids: list[int],
        tool_names: list[str],
        skip_tool_names: list[str],
        segments: list[str],
        arg_profile_ids: list[int],
    ) -> None: ...
    def delete(self, saved_scan_id: int) -> None: ...
