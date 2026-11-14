"""Domain port for Burp Suite REST API operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from infrastructure.tools.burp.models import (
        BurpScanProgress,
        BurpScanRequest,
    )


class BurpApiError(Exception):
    """Raised when the Burp REST API returns an error."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"Burp API ({status_code}): {message}")


class BurpRestClientPort(Protocol):
    """Contract for communicating with Burp's REST API."""

    def health_check(self) -> bool: ...

    def create_scan(self, request: BurpScanRequest) -> str: ...

    def get_scan_progress(
        self,
        task_id: str,
        *,
        after: int = 0,
        max_issue_events: int = 100,
    ) -> BurpScanProgress: ...
