"""Re-exports from domain.locking.cancellation."""

from domain.locking.cancellation import CancellationToken, no_op_token

__all__ = ["CancellationToken", "no_op_token"]
