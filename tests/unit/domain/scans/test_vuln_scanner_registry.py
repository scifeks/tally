import pytest

from domain.scans.vuln_scanner_registry import (
    UnknownScannerSkill,
    group_by_family,
    list_scanners,
    resolve_display_slug,
    resolve_full_slug,
)


def test_list_scanners_returns_entries_with_stripped_display_slug() -> None:
    entries = list_scanners()
    assert len(entries) > 0
    for entry in entries:
        assert entry.full_slug.startswith("tally-")
        assert not entry.display_slug.startswith("tally-")
        assert entry.full_slug == f"tally-{entry.display_slug}"


def test_resolve_display_slug_roundtrips() -> None:
    first = list_scanners()[0]
    assert resolve_display_slug(first.display_slug) == first.full_slug


def test_resolve_display_slug_rejects_unknown() -> None:
    with pytest.raises(UnknownScannerSkill):
        resolve_display_slug("scan-this-does-not-exist")


def test_resolve_display_slug_rejects_full_slug_form() -> None:
    full = list_scanners()[0].full_slug
    with pytest.raises(UnknownScannerSkill):
        resolve_display_slug(full)


def test_group_by_family_covers_all_entries() -> None:
    all_entries = list_scanners()
    grouped = group_by_family()
    flat = [e for family in grouped.values() for e in family]
    assert sorted(e.full_slug for e in flat) == sorted(e.full_slug for e in all_entries)


def test_resolve_full_slug_roundtrips() -> None:
    first = list_scanners()[0]
    assert resolve_full_slug(first.full_slug) == first.display_slug


def test_resolve_full_slug_rejects_unknown() -> None:
    with pytest.raises(UnknownScannerSkill):
        resolve_full_slug("tally-scan-this-does-not-exist")
