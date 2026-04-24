"""Severity value object — single source of truth for label↔rank mapping."""

from __future__ import annotations

from domain.tools.constants import SEVERITY_LEVELS

_LABEL_RANKS: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}

_RANK_LABELS: dict[int, str] = {v: k for k, v in _LABEL_RANKS.items()}


class Severity:
    """Immutable pairing of a severity label and its integer rank.

    Lower rank = more severe. ``critical`` is rank 0; ``informational`` is
    rank 4.  The integer rank is what is stored in the ``findings.severity``
    SQLite column so that ``ORDER BY severity ASC`` yields the correct
    semantic order without SQL CASE expressions.
    """

    __slots__ = ("_label", "_rank")

    def __init__(self, label: str, rank: int) -> None:
        self._label = label
        self._rank = rank

    @classmethod
    def from_label(cls, label: str) -> Severity:
        """Return the Severity for *label* (case-insensitive).

        Raises ``ValueError`` for unknown labels.
        """
        key = label.lower()
        if key not in _LABEL_RANKS:
            raise ValueError(
                f"Unknown severity label {label!r}. "
                f"Valid labels: {sorted(_LABEL_RANKS)}"
            )
        return cls(key, _LABEL_RANKS[key])

    @classmethod
    def from_rank(cls, rank: int) -> Severity:
        """Return the Severity for integer *rank*.

        Raises ``ValueError`` for unknown ranks.
        """
        if rank not in _RANK_LABELS:
            raise ValueError(
                f"Unknown severity rank {rank!r}. Valid ranks: {sorted(_RANK_LABELS)}"
            )
        label = _RANK_LABELS[rank]
        return cls(label, rank)

    @property
    def label(self) -> str:
        """Human-readable severity label, e.g. ``'critical'``."""
        return self._label

    @property
    def rank(self) -> int:
        """Integer rank; lower is more severe."""
        return self._rank

    @classmethod
    def all_ordered(cls) -> list[Severity]:
        """Return all severities ordered from most to least severe."""
        return [cls(lbl, rank) for rank, lbl in sorted(_RANK_LABELS.items())]

    @classmethod
    def valid_labels(cls) -> frozenset[str]:
        """Return the set of valid severity label strings."""
        return frozenset(SEVERITY_LEVELS)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Severity):
            return self._rank == other._rank
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._rank)

    def __repr__(self) -> str:
        return f"Severity(label={self._label!r}, rank={self._rank})"
