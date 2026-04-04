"""Unit tests for SEGMENT_ORDER constant."""

from __future__ import annotations

from domain.tools.scan_types.models import SEGMENT_ORDER

_EXPECTED = {"sast", "sca", "secrets", "api"}


def test_is_a_list() -> None:
    assert isinstance(SEGMENT_ORDER, list)


def test_contains_all_expected_segments() -> None:
    assert set(SEGMENT_ORDER) == _EXPECTED


def test_has_no_duplicates() -> None:
    assert len(SEGMENT_ORDER) == len(set(SEGMENT_ORDER))
