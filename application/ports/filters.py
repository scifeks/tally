"""Filter AST used at the VectorIndex port boundary.

Application code composes filters with these dataclasses; the adapter
translates them into its storage-engine DSL. Closed set today: Eq, Contains,
And, Or.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Eq:
    field: str
    value: str | int | float | bool


@dataclass(frozen=True)
class Contains:
    field: str
    substring: str


@dataclass(frozen=True)
class And:
    clauses: tuple[Filter, ...]


@dataclass(frozen=True)
class Or:
    clauses: tuple[Filter, ...]


type Filter = Eq | Contains | And | Or
