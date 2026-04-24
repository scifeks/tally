"""Unit tests for domain.findings.sort enums."""

from __future__ import annotations

import pytest

from domain.findings.sort import FindingSortColumn, InvalidSortColumn, SortDirection


class TestFindingSortColumn:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("severity", FindingSortColumn.SEVERITY),
            ("status", FindingSortColumn.STATUS),
            ("tool", FindingSortColumn.TOOL),
            ("first_seen", FindingSortColumn.FIRST_SEEN),
            ("last_seen", FindingSortColumn.LAST_SEEN),
            ("title", FindingSortColumn.TITLE),
        ],
    )
    def test_from_label_known(self, label: str, expected: FindingSortColumn) -> None:
        assert FindingSortColumn.from_label(label) == expected

    def test_case_insensitive(self) -> None:
        assert FindingSortColumn.from_label("SEVERITY") == FindingSortColumn.SEVERITY
        assert (
            FindingSortColumn.from_label("First_Seen") == FindingSortColumn.FIRST_SEEN
        )

    def test_unknown_raises_invalid_sort_column(self) -> None:
        with pytest.raises(InvalidSortColumn):
            FindingSortColumn.from_label("bogus")

    def test_invalid_sort_column_is_value_error_subclass(self) -> None:
        with pytest.raises(ValueError):
            FindingSortColumn.from_label("bogus")

    def test_title_sql_expr(self) -> None:
        assert FindingSortColumn.TITLE.sql_expr == "json_extract(meta, '$.title')"

    def test_severity_sql_expr(self) -> None:
        assert FindingSortColumn.SEVERITY.sql_expr == "severity"

    def test_first_seen_sql_expr(self) -> None:
        assert FindingSortColumn.FIRST_SEEN.sql_expr == "first_seen"

    def test_last_seen_sql_expr(self) -> None:
        assert FindingSortColumn.LAST_SEEN.sql_expr == "last_seen"


class TestSortDirection:
    def test_asc_from_label(self) -> None:
        assert SortDirection.from_label("asc") == SortDirection.ASC

    def test_desc_from_label(self) -> None:
        assert SortDirection.from_label("desc") == SortDirection.DESC

    def test_case_insensitive(self) -> None:
        assert SortDirection.from_label("ASC") == SortDirection.ASC
        assert SortDirection.from_label("DESC") == SortDirection.DESC

    def test_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            SortDirection.from_label("bogus")

    def test_values(self) -> None:
        assert SortDirection.ASC.value == "ASC"
        assert SortDirection.DESC.value == "DESC"
