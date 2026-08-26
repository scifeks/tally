"""Configuration for a Burp Suite scan execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BurpScanConfig:
    """Immutable configuration passed to BurpScanExecutor."""

    urls: list[str] = field(default_factory=list)
    timeout: int | None = None
    config_name: str | None = None
