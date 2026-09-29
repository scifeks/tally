"""Tests for Burp scan polling backoff calculation."""

from __future__ import annotations

import pytest

from infrastructure.tools.burp.backoff import calculate_backoff


class TestCalculateBackoff:
    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [
            (0, 5.0),
            (1, 10.0),
            (2, 20.0),
            (3, 30.0),
            (4, 30.0),
            (5, 30.0),
            (10, 30.0),
        ],
        ids=[
            "initial_5s",
            "second_10s",
            "third_20s",
            "fourth_capped_30s",
            "fifth_still_30s",
            "sixth_still_30s",
            "tenth_still_30s",
        ],
    )
    def test_backoff_progression(self, attempt: int, expected: float) -> None:
        assert calculate_backoff(attempt) == expected
