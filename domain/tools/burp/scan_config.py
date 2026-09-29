"""Configuration for a Burp Suite scan execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BurpScanConfig:
    """Immutable configuration passed to BurpScanExecutor."""

    urls: list[str] = field(default_factory=list)
    timeout: int | None = None
    task_name: str | None = None
    config_names: list[str] = field(default_factory=list)
