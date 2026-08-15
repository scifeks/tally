"""Unit tests for the duplicate-candidates grouping helper."""

from __future__ import annotations

from application.mcp.duplicate_grouping import (
    GroupableFinding,
    group_duplicate_candidates,
)


def _f(
    fid: int,
    file: str = "src/a.py",
    rule_id: str = "xss.stored",
    line_start: int | None = 10,
    line_end: int | None = 15,
) -> GroupableFinding:
    return GroupableFinding(
        id=fid,
        file=file,
        rule_id=rule_id,
        line_start=line_start,
        line_end=line_end,
    )


class TestGroupDuplicateCandidates:
    """Tests for duplicate candidate grouping."""

    def test_empty_input(self) -> None:
        """Empty input returns empty list."""
        assert group_duplicate_candidates([]) == []

    def test_singleton_not_returned(self) -> None:
        """Single finding is not returned."""
        assert group_duplicate_candidates([_f(1)]) == []

    def test_overlapping_same_family_grouped(self) -> None:
        """Overlapping ranges with same family are grouped."""
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=12, line_end=18)
        assert group_duplicate_candidates([a, b]) == [[1, 2]]

    def test_within_default_proximity_grouped(self) -> None:
        """Ranges within default proximity are grouped."""
        # a ends at 15; b starts at 20, gap of 5 lines.
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=20, line_end=25)
        assert group_duplicate_candidates([a, b]) == [[1, 2]]

    def test_beyond_default_proximity_not_grouped(self) -> None:
        """Ranges beyond default proximity are not grouped."""
        # a ends at 15; b starts at 26, gap of 11 lines.
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=26, line_end=30)
        assert group_duplicate_candidates([a, b]) == []

    def test_different_family_not_grouped(self) -> None:
        """Different rule families are not grouped."""
        a = _f(1, rule_id="xss.stored", line_start=10, line_end=15)
        b = _f(2, rule_id="injection.sql", line_start=10, line_end=15)
        assert group_duplicate_candidates([a, b]) == []

    def test_different_file_not_grouped(self) -> None:
        """Different files are not grouped."""
        a = _f(1, file="src/a.py")
        b = _f(2, file="src/b.py")
        assert group_duplicate_candidates([a, b]) == []

    def test_three_pairwise_groupable_single_group(self) -> None:
        """Three pairwise groupable findings form single group."""
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=12, line_end=18)
        c = _f(3, line_start=14, line_end=20)
        groups = group_duplicate_candidates([a, b, c])
        assert groups == [[1, 2, 3]]

    def test_tunable_proximity(self) -> None:
        """Proximity parameter is respected."""
        # 20 lines apart, no overlap.
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=35, line_end=40)
        assert group_duplicate_candidates([a, b], proximity=25) == [[1, 2]]

    def test_missing_line_end_single_line(self) -> None:
        """Missing line_end treats finding as single line."""
        # No line_end → treat as line_start == line_end (single-line finding).
        a = _f(1, line_start=10, line_end=None)
        b = _f(2, line_start=12, line_end=15)
        assert group_duplicate_candidates([a, b]) == [[1, 2]]

    def test_same_rule_id_no_dot_still_families(self) -> None:
        """Rule ID without dot: family is whole rule_id."""
        a = _f(1, rule_id="ssrf")
        b = _f(2, rule_id="ssrf")
        assert group_duplicate_candidates([a, b]) == [[1, 2]]

    def test_transitive_grouping(self) -> None:
        """Transitive closure creates single group via intermediate."""
        # a↔b overlaps, b↔c overlaps, a and c far apart: still one group via b.
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=18, line_end=25)
        c = _f(3, line_start=28, line_end=35)
        # a-b: 3-line gap; b-c: 3-line gap. Default proximity 10 = all one group.
        assert group_duplicate_candidates([a, b, c]) == [[1, 2, 3]]

    def test_null_file_not_grouped(self) -> None:
        """Findings with None file are not grouped."""
        a = GroupableFinding(
            id=1,
            file=None,
            rule_id="xss.stored",
            line_start=10,
            line_end=15,
        )
        b = GroupableFinding(
            id=2,
            file=None,
            rule_id="xss.stored",
            line_start=10,
            line_end=15,
        )
        assert group_duplicate_candidates([a, b]) == []

    def test_null_rule_id_not_grouped(self) -> None:
        """Findings with None rule_id are not grouped."""
        a = GroupableFinding(
            id=1,
            file="src/a.py",
            rule_id=None,
            line_start=10,
            line_end=15,
        )
        b = GroupableFinding(
            id=2,
            file="src/a.py",
            rule_id=None,
            line_start=10,
            line_end=15,
        )
        assert group_duplicate_candidates([a, b]) == []

    def test_null_line_start_not_grouped(self) -> None:
        """Findings with None line_start are not grouped."""
        a = GroupableFinding(
            id=1,
            file="src/a.py",
            rule_id="xss.stored",
            line_start=None,
            line_end=15,
        )
        b = GroupableFinding(
            id=2,
            file="src/a.py",
            rule_id="xss.stored",
            line_start=10,
            line_end=15,
        )
        assert group_duplicate_candidates([a, b]) == []

    def test_multiple_groups(self) -> None:
        """Multiple independent groups are returned."""
        a = _f(1, line_start=10, line_end=15)
        b = _f(2, line_start=12, line_end=18)
        c = _f(3, line_start=100, line_end=105)
        d = _f(4, line_start=102, line_end=108)
        groups = group_duplicate_candidates([a, b, c, d])
        assert sorted(groups) == [[1, 2], [3, 4]]

    def test_deterministic_ordering(self) -> None:
        """Groups and members are sorted deterministically."""
        # Insert in non-sorted order
        findings = [
            _f(5, line_start=100, line_end=105),
            _f(2, line_start=12, line_end=18),
            _f(4, line_start=102, line_end=108),
            _f(1, line_start=10, line_end=15),
        ]
        groups = group_duplicate_candidates(findings)
        # Should be sorted by smallest member, then members within each group
        assert groups == [[1, 2], [4, 5]]
