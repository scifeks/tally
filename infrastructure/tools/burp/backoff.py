"""Exponential backoff for Burp scan polling.

Starts at 5 seconds, doubles each attempt, caps at 30 seconds.
"""

from __future__ import annotations

_INITIAL_DELAY = 5.0
_MAX_DELAY = 30.0


def calculate_backoff(attempt: int) -> float:
    """Return the poll delay in seconds for the given attempt number.

    Progression: 5, 10, 20, 30, 30, 30...
    """
    return min(_INITIAL_DELAY * (2**attempt), _MAX_DELAY)
