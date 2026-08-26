"""Request/response DTOs for the Burp REST API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BurpScanRequest:
    """POST /v0.1/scan body."""

    urls: list[str]
    name: str | None = None
    scan_configurations: list[str] | None = None


@dataclass(frozen=True)
class BurpScanProgress:
    """GET /v0.1/scan/{task_id} response."""

    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    issue_events: list[dict[str, Any]] = field(default_factory=list)
