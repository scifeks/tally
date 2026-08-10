"""Application-layer service for saved scans.

CRUD orchestration with structured validation. Depends on the saved-
scans repository port, the tool-arg-profiles repository port for
membership checks against existing profile ids, and the in-process
ToolRegistry for tool-name membership checks. No infrastructure
imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.saved_scans.errors import StaleSavedScanError
from domain.saved_scans.entry import (
    StaleSavedScanArgProfileItem,
    StaleSavedScanItem,
    StaleSavedScanRepoItem,
    StaleSavedScanToolItem,
)
from domain.tools.scan_types.models import SEGMENT_ORDER

if TYPE_CHECKING:
    from application.ports.saved_scans import SavedScansRepositoryPort
    from application.ports.tool_arg_profiles import (
        ToolArgProfilesRepositoryPort,
    )
    from application.tools.registry import ToolRegistry
    from domain.saved_scans.entry import (
        SavedScanHydrated,
        SavedScanListItem,
    )


@dataclass(frozen=True)
class FieldError:
    """Single field validation error."""

    field: str
    issue: str


class SavedScanValidationError(Exception):
    """Raised when one or more validation rules fail."""

    def __init__(self, fields: list[FieldError]) -> None:
        self.fields: tuple[FieldError, ...] = tuple(fields)
        super().__init__(f"validation failed: {len(self.fields)} field error(s)")


class SavedScanNotFound(Exception):
    """Raised when no saved scan exists for the given id."""

    def __init__(self, saved_scan_id: int) -> None:
        self.saved_scan_id = saved_scan_id
        super().__init__(f"saved_scan id {saved_scan_id} not found")


class SavedScansService:
    """Application service for saved scans."""

    def __init__(
        self,
        repo: SavedScansRepositoryPort,
        profiles_repo: ToolArgProfilesRepositoryPort,
        tool_registry: ToolRegistry,
    ) -> None:
        self._repo = repo
        self._profiles_repo = profiles_repo
        self._tool_registry = tool_registry

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SavedScanListItem], int]:
        """List saved scans with pagination."""
        return self._repo.list_for_project(offset=offset, limit=limit)

    def get(self, saved_scan_id: int) -> SavedScanHydrated | None:
        """Return the hydrated saved scan, or None when absent."""
        return self._repo.get_hydrated(saved_scan_id)

    def create(
        self,
        *,
        name: str,
        skip_enrichment: bool,
        repo_ids: list[int],
        tool_names: list[str],
        skip_tool_names: list[str],
        segments: list[str],
        arg_profile_ids: list[int],
    ) -> SavedScanHydrated:
        """Create a new saved scan.

        Validates inputs first; raises SavedScanValidationError on any
        failure. Propagates SavedScanNameConflict from the repository.
        Returns the freshly hydrated saved scan.
        """
        self._validate_input(
            name=name,
            tool_names=tool_names,
            skip_tool_names=skip_tool_names,
            segments=segments,
            arg_profile_ids=arg_profile_ids,
        )
        new_id = self._repo.insert(
            name=name,
            skip_enrichment=skip_enrichment,
            repo_ids=repo_ids,
            tool_names=tool_names,
            skip_tool_names=skip_tool_names,
            segments=segments,
            arg_profile_ids=arg_profile_ids,
        )
        result = self._repo.get_hydrated(new_id)
        assert result is not None
        return result

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
    ) -> SavedScanHydrated:
        """Replace an existing saved scan.

        Validates inputs first. Reads the current row to detect missing
        ids early; raises SavedScanNotFound when the row does not exist.
        Propagates SavedScanNameConflict from the repository. Returns
        the freshly hydrated saved scan.
        """
        self._validate_input(
            name=name,
            tool_names=tool_names,
            skip_tool_names=skip_tool_names,
            segments=segments,
            arg_profile_ids=arg_profile_ids,
        )
        existing = self._repo.get_hydrated(saved_scan_id)
        if existing is None:
            raise SavedScanNotFound(saved_scan_id)
        self._repo.replace(
            saved_scan_id,
            name=name,
            skip_enrichment=skip_enrichment,
            repo_ids=repo_ids,
            tool_names=tool_names,
            skip_tool_names=skip_tool_names,
            segments=segments,
            arg_profile_ids=arg_profile_ids,
        )
        result = self._repo.get_hydrated(saved_scan_id)
        assert result is not None
        return result

    def delete(self, saved_scan_id: int) -> None:
        """Delete the saved scan; cascades join rows via the schema.

        The route layer maps the missing-id case to 404 by querying
        first.
        """
        self._repo.delete(saved_scan_id)

    def run_saved_scan(self, saved_scan_id: int) -> SavedScanHydrated:
        """Load a saved scan and validate all references still exist.

        Raises SavedScanNotFound if the saved scan does not exist.
        Raises StaleSavedScanError if any repo is soft-deleted, any
        tool is unregistered, or any arg profile no longer exists.
        Returns the hydrated saved scan if validation passes.
        """
        hydrated = self._repo.get_hydrated(saved_scan_id)
        if hydrated is None:
            raise SavedScanNotFound(saved_scan_id)

        stale: list[StaleSavedScanItem] = []

        for r in hydrated.repos:
            if r.deleted_at is not None:
                stale.append(StaleSavedScanRepoItem(id=r.id, name=r.name))

        registered = set(self._tool_registry.list_tool_names())
        for t in hydrated.tools:
            if t.tool_name not in registered:
                stale.append(StaleSavedScanToolItem(name=t.tool_name))

        raw_profile_ids = self._repo.list_arg_profile_ids(saved_scan_id)
        if raw_profile_ids:
            present = set(self._profiles_repo.existing_ids(raw_profile_ids))
            for pid in raw_profile_ids:
                if pid not in present:
                    stale.append(StaleSavedScanArgProfileItem(id=pid))

        if stale:
            raise StaleSavedScanError(stale)

        return hydrated

    def _validate_input(
        self,
        *,
        name: str,
        tool_names: list[str],
        skip_tool_names: list[str],
        segments: list[str],
        arg_profile_ids: list[int],
    ) -> None:
        """Collect every field error in one pass before raising."""
        errors: list[FieldError] = []

        if not name:
            errors.append(FieldError(field="name", issue="must not be empty"))

        if not tool_names and not arg_profile_ids and not skip_tool_names:
            errors.append(
                FieldError(
                    field="toolNames",
                    issue=(
                        "at least one of toolNames, skipToolIds,"
                        " or argProfileIds must be non-empty"
                    ),
                )
            )

        registered = set(self._tool_registry.list_tool_names())

        if tool_names:
            for idx, n in enumerate(tool_names):
                if n not in registered:
                    errors.append(
                        FieldError(
                            field=f"toolNames[{idx}]",
                            issue=f"unknown tool name {n!r}",
                        )
                    )

        if skip_tool_names:
            for idx, n in enumerate(skip_tool_names):
                if n not in registered:
                    errors.append(
                        FieldError(
                            field=f"skipToolNames[{idx}]",
                            issue=f"unknown tool name {n!r}",
                        )
                    )

        if segments:
            valid_segments = set(SEGMENT_ORDER)
            for idx, seg in enumerate(segments):
                if seg not in valid_segments:
                    errors.append(
                        FieldError(
                            field=f"segments[{idx}]",
                            issue=f"unknown segment {seg!r}",
                        )
                    )

        if arg_profile_ids:
            existing = set(self._profiles_repo.existing_ids(arg_profile_ids))
            for idx, pid in enumerate(arg_profile_ids):
                if pid not in existing:
                    errors.append(
                        FieldError(
                            field=f"argProfileIds[{idx}]",
                            issue=f"unknown arg profile id {pid}",
                        )
                    )

        if errors:
            raise SavedScanValidationError(errors)
