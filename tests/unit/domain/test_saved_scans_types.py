"""Unit tests for domain.saved_scans.entry dataclasses."""

from __future__ import annotations

import pytest

from domain.saved_scans.entry import (
    SavedScan,
    SavedScanArgProfileRef,
    SavedScanHydrated,
    SavedScanRepoRef,
    SavedScanToolRef,
    StaleSavedScanArgProfileItem,
    StaleSavedScanItem,
    StaleSavedScanRepoItem,
    StaleSavedScanToolItem,
)


class TestSavedScan:
    def test_fields_accessible(self) -> None:
        scan = SavedScan(
            id=3,
            name="Weekly secrets sweep",
            skip_enrichment=False,
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        assert scan.id == 3
        assert scan.name == "Weekly secrets sweep"
        assert scan.skip_enrichment is False

    def test_is_frozen(self) -> None:
        scan = SavedScan(
            id=1,
            name="x",
            skip_enrichment=False,
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        with pytest.raises(Exception):
            scan.name = "y"  # type: ignore[misc]


class TestSavedScanRepoRef:
    def test_carries_deleted_at(self) -> None:
        ref = SavedScanRepoRef(id=5, name="auth-service", deleted_at=None)
        assert ref.deleted_at is None
        deleted = SavedScanRepoRef(
            id=6, name="legacy-svc", deleted_at="2026-04-01T00:00:00Z"
        )
        assert deleted.deleted_at == "2026-04-01T00:00:00Z"


class TestSavedScanHydrated:
    def test_holds_all_ref_lists(self) -> None:
        scan = SavedScan(
            id=3,
            name="Weekly secrets sweep",
            skip_enrichment=False,
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        hydrated = SavedScanHydrated(
            saved_scan=scan,
            repos=[SavedScanRepoRef(id=1, name="auth-service", deleted_at=None)],
            tools=[SavedScanToolRef(tool_name="gitleaks")],
            arg_profiles=[
                SavedScanArgProfileRef(id=12, tool_name="gitleaks", name="verbose-scan")
            ],
        )
        assert hydrated.saved_scan is scan
        assert hydrated.repos[0].name == "auth-service"
        assert hydrated.tools[0].tool_name == "gitleaks"
        assert hydrated.arg_profiles[0].name == "verbose-scan"


class TestStaleSavedScanItems:
    def test_repo_item_kind(self) -> None:
        item = StaleSavedScanRepoItem(id=5, name="deleted-repo")
        assert item.kind == "repo"
        assert item.id == 5
        assert item.name == "deleted-repo"

    def test_tool_item_kind(self) -> None:
        item = StaleSavedScanToolItem(name="old-tool")
        assert item.kind == "tool"
        assert item.name == "old-tool"

    def test_arg_profile_item_kind(self) -> None:
        item = StaleSavedScanArgProfileItem(id=99)
        assert item.kind == "argProfile"
        assert item.id == 99

    def test_alias_accepts_each_variant(self) -> None:
        items: list[StaleSavedScanItem] = [
            StaleSavedScanRepoItem(id=5, name="deleted-repo"),
            StaleSavedScanToolItem(name="old-tool"),
            StaleSavedScanArgProfileItem(id=99),
        ]
        kinds = [item.kind for item in items]
        assert kinds == ["repo", "tool", "argProfile"]
