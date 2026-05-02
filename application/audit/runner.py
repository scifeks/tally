"""Invoke an async function and persist an audit record for the call."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.ports.audit_repository import AuditRepositoryPort


class AuditRunner:
    """Calls an async fn and writes one audit row regardless of success/failure."""

    def __init__(self, audit_repo: AuditRepositoryPort) -> None:
        self._audit_repo = audit_repo

    async def run(
        self,
        tool_name: str,
        arguments: dict,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Invoke *fn* and persist an audit record for the call."""
        start = datetime.now(UTC)
        error: str | None = None
        result = None
        try:
            result = await fn(*args, **kwargs)
        except NotImplementedError:
            error = "not implemented"
            raise
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
            await asyncio.to_thread(
                self._audit_repo.log_event,
                tool_name,
                arguments,
                error is None,
                error,
                duration_ms,
            )
        return result
