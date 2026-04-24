"""Sort column whitelist and direction enum for findings queries."""

from __future__ import annotations

from enum import Enum


class InvalidSortColumn(ValueError):
    """Raised when an unrecognised sort column name is supplied."""


class FindingSortColumn(Enum):
    """Allowed sort columns for findings queries.

    Enum values are the SQL expressions used in ``ORDER BY``.
    """

    SEVERITY = "severity"
    STATUS = "status"
    TOOL = "tool"
    FIRST_SEEN = "first_seen"
    LAST_SEEN = "last_seen"
    TITLE = "json_extract(meta, '$.title')"

    @classmethod
    def from_label(cls, label: str) -> FindingSortColumn:
        """Return the column for *label* (case-insensitive).

        Raises ``InvalidSortColumn`` for unknown names.
        """
        normalised = label.lower()
        mapping = {member.name.lower(): member for member in cls}
        if normalised not in mapping:
            raise InvalidSortColumn(
                f"Unknown sort column {label!r}. Valid columns: {sorted(mapping)}"
            )
        return mapping[normalised]

    @property
    def sql_expr(self) -> str:
        """SQL expression to use in ORDER BY."""
        return self.value


class SortDirection(Enum):
    """Sort direction for findings queries."""

    ASC = "ASC"
    DESC = "DESC"

    @classmethod
    def from_label(cls, label: str) -> SortDirection:
        """Return the direction for *label* (case-insensitive).

        Raises ``ValueError`` for unknown directions.
        """
        normalised = label.upper()
        try:
            return cls(normalised)
        except ValueError:
            raise ValueError(f"Unknown sort direction {label!r}. Valid: 'asc', 'desc'")
