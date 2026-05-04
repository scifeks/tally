"""Domain entries for saved scans and their hydrated joins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SavedScan:
    id: int
    name: str
    skip_enrichment: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SavedScanRepoRef:
    id: int
    name: str
    deleted_at: str | None


@dataclass(frozen=True)
class SavedScanToolRef:
    tool_name: str


@dataclass(frozen=True)
class SavedScanArgProfileRef:
    id: int
    tool_name: str
    name: str


@dataclass(frozen=True)
class SavedScanReference:
    """Minimal saved-scan reference used in cross-aggregate IN_USE responses."""

    id: int
    name: str


@dataclass(frozen=True)
class SavedScanHydrated:
    saved_scan: SavedScan
    repos: list[SavedScanRepoRef]
    tools: list[SavedScanToolRef]
    arg_profiles: list[SavedScanArgProfileRef]


@dataclass(frozen=True)
class SavedScanListItem:
    saved_scan: SavedScan
    repo_ids: list[int]
    tool_names: list[str]
    arg_profile_ids: list[int]


@dataclass(frozen=True)
class StaleSavedScanRepoItem:
    id: int
    name: str | None
    kind: Literal["repo"] = "repo"


@dataclass(frozen=True)
class StaleSavedScanToolItem:
    name: str
    kind: Literal["tool"] = "tool"


@dataclass(frozen=True)
class StaleSavedScanArgProfileItem:
    id: int
    kind: Literal["argProfile"] = "argProfile"


type StaleSavedScanItem = (
    StaleSavedScanRepoItem | StaleSavedScanToolItem | StaleSavedScanArgProfileItem
)
