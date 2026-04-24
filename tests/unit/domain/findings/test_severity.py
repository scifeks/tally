"""Unit tests for domain.findings.severity.Severity value object."""

from __future__ import annotations

import pytest

from domain.findings.severity import Severity


class TestFromLabel:
    def test_critical_rank(self) -> None:
        assert Severity.from_label("critical").rank == 0

    def test_high_rank(self) -> None:
        assert Severity.from_label("high").rank == 1

    def test_medium_rank(self) -> None:
        assert Severity.from_label("medium").rank == 2

    def test_low_rank(self) -> None:
        assert Severity.from_label("low").rank == 3

    def test_informational_rank(self) -> None:
        assert Severity.from_label("informational").rank == 4

    def test_case_insensitive(self) -> None:
        assert Severity.from_label("CRITICAL").rank == 0
        assert Severity.from_label("High").rank == 1

    def test_unknown_label_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown severity label"):
            Severity.from_label("bogus")

    def test_empty_label_raises(self) -> None:
        with pytest.raises(ValueError):
            Severity.from_label("")


class TestFromRank:
    @pytest.mark.parametrize(
        ("rank", "expected_label"),
        [
            (0, "critical"),
            (1, "high"),
            (2, "medium"),
            (3, "low"),
            (4, "informational"),
        ],
    )
    def test_round_trip(self, rank: int, expected_label: str) -> None:
        sev = Severity.from_rank(rank)
        assert sev.label == expected_label
        assert sev.rank == rank

    def test_unknown_rank_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown severity rank"):
            Severity.from_rank(99)

    def test_negative_rank_raises(self) -> None:
        with pytest.raises(ValueError):
            Severity.from_rank(-1)


class TestAllOrdered:
    def test_length(self) -> None:
        assert len(Severity.all_ordered()) == 5

    def test_label_order(self) -> None:
        labels = [s.label for s in Severity.all_ordered()]
        assert labels == ["critical", "high", "medium", "low", "informational"]

    def test_ranks_are_strictly_ascending(self) -> None:
        ranks = [s.rank for s in Severity.all_ordered()]
        assert ranks == sorted(ranks)
        assert len(ranks) == len(set(ranks))


class TestValidLabels:
    def test_all_five_labels_present(self) -> None:
        labels = Severity.valid_labels()
        assert labels == frozenset(
            {"critical", "high", "medium", "low", "informational"}
        )


class TestRoundTrip:
    @pytest.mark.parametrize(
        "label",
        ["critical", "high", "medium", "low", "informational"],
    )
    def test_label_rank_label(self, label: str) -> None:
        assert Severity.from_rank(Severity.from_label(label).rank).label == label
