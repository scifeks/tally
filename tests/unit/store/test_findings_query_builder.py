"""Unit tests for FindingQueryBuilder duplicate_of IS NULL filter."""

from __future__ import annotations

from infrastructure.store.repositories.findings_query import FindingQueryBuilder


class TestDuplicateOfIsNullFilter:
    """Test that duplicate_of IS NULL is always appended to WHERE clauses."""

    def test_build_where_parts_empty_filters(self) -> None:
        """Empty filters should return only the duplicate_of IS NULL clause."""
        builder = FindingQueryBuilder({})
        where_parts, params = builder.build_where_parts()

        assert len(where_parts) == 1
        assert where_parts[0] == "duplicate_of IS NULL"
        assert params == []

    def test_build_where_parts_with_conditions(self) -> None:
        """Conditions should be combined with duplicate_of IS NULL."""
        builder = FindingQueryBuilder(
            {
                "conditions": [
                    ("tool", "=", ["semgrep"]),
                    ("severity", "=", ["high"]),
                ]
            }
        )
        where_parts, params = builder.build_where_parts()

        assert "duplicate_of IS NULL" in where_parts
        assert len(where_parts) == 3
        assert params == ["semgrep", 1]

    def test_build_with_duplicate_filter(self) -> None:
        """Full SQL build should include duplicate_of IS NULL in WHERE."""
        builder = FindingQueryBuilder({})
        sql, params = builder.build()

        assert "WHERE duplicate_of IS NULL" in sql
        assert len(params) == 2
        assert params == [200, 0]

    def test_build_with_conditions_and_duplicate_filter(self) -> None:
        """SQL with conditions should include duplicate_of IS NULL."""
        builder = FindingQueryBuilder(
            {
                "conditions": [
                    ("tool", "=", ["semgrep"]),
                ]
            }
        )
        sql, _ = builder.build()

        assert "duplicate_of IS NULL" in sql
        assert "tool IN" in sql or "tool =" in sql

    def test_build_count_with_duplicate_filter(self) -> None:
        """COUNT query should include duplicate_of IS NULL."""
        builder = FindingQueryBuilder({})
        sql, params = builder.build_count()

        assert "WHERE duplicate_of IS NULL" in sql
        assert params == []

    def test_build_count_with_conditions_and_duplicate_filter(self) -> None:
        """COUNT query with conditions should include duplicate_of IS NULL."""
        builder = FindingQueryBuilder(
            {
                "conditions": [
                    ("severity", "=", ["critical"]),
                ]
            }
        )
        sql, _ = builder.build_count()

        assert "duplicate_of IS NULL" in sql
        assert "SELECT COUNT(*)" in sql

    def test_duplicate_filter_with_search(self) -> None:
        """Search term should combine with duplicate_of IS NULL."""
        builder = FindingQueryBuilder(
            {
                "search": "test",
            }
        )
        where_parts, params = builder.build_where_parts()

        assert "duplicate_of IS NULL" in where_parts
        # Search adds 6 params for the 6 fields in the search predicate.
        assert len(params) == 6

    def test_duplicate_filter_appears_last(self) -> None:
        """duplicate_of IS NULL should be the last clause."""
        builder = FindingQueryBuilder(
            {
                "conditions": [
                    ("tool", "=", ["gitleaks"]),
                ]
            }
        )
        where_parts, _ = builder.build_where_parts()

        assert where_parts[-1] == "duplicate_of IS NULL"
