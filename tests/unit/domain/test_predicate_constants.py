"""Verify predicate constant sets are defined and non-empty."""

from __future__ import annotations

from domain.tools.constants import (
    ACCESS_REQUIRED_LEVELS,
    EXPLOITATION_COMPLEXITY_LEVELS,
    USER_INTERACTION_LEVELS,
)


class TestPredicateConstants:
    def test_access_required_values(self) -> None:
        assert ACCESS_REQUIRED_LEVELS == {
            "none",
            "authenticated",
            "privileged",
        }

    def test_exploitation_complexity_values(self) -> None:
        assert EXPLOITATION_COMPLEXITY_LEVELS == {
            "low",
            "high",
        }

    def test_user_interaction_values(self) -> None:
        assert USER_INTERACTION_LEVELS == {
            "none",
            "required",
        }
