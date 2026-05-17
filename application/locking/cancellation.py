"""Cancellation token for cooperative scan abort.

A scan thread checks ``token.is_set()`` between segments, between tool
launches, and inside ``ToolExecutor`` while waiting on a subprocess. The
HTTP cancel endpoint sets the token; the scan thread observes it and
unwinds gracefully, emitting ``run_canceled`` and persisting
``status='canceled'`` before exiting.

The REPL passes a ``no_op_token()`` since the REPL has no UX to cancel
mid-scan; only the API surface needs cooperative cancellation.
"""

from __future__ import annotations

import threading


class CancellationToken:
    """Thread-safe cooperative cancellation flag.

    Wraps ``threading.Event``. ``set()`` requests cancellation;
    ``is_set()`` is the polling check; ``wait(timeout)`` blocks until
    either cancellation or timeout. The token is one-way: once set, it
    stays set for the lifetime of the scan.
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        """Request cancellation. Idempotent."""
        self._event.set()

    def is_set(self) -> bool:
        """Return True if cancellation was requested."""
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until cancellation; return True if it was set."""
        return self._event.wait(timeout)


_NO_OP: CancellationToken | None = None


def no_op_token() -> CancellationToken:
    """Return a shared, never-cancelled token for REPL / test paths.

    The token is process-singleton: cheap to share across calls, and
    nothing ever sets it.
    """
    global _NO_OP
    if _NO_OP is None:
        _NO_OP = CancellationToken()
    return _NO_OP
