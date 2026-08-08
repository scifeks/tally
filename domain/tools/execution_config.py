"""Execution-time config snapshots threaded into tool wrappers.

Snapshots are built at the application boundary from `ConfigManager`
state and frozen so wrappers cannot mutate them. Keeping the shape
narrow means the domain stays free of references to outward
configuration types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NoirProviderSnapshot:
    base_url: str
    model: str
    num_ctx: int | None


@dataclass(frozen=True)
class ToolExecutionConfig:
    noir_provider: NoirProviderSnapshot | None
    blind_xss_callback_url: str = ""
    antares_config: Any = None
    ffuf_wordlist_path: str = ""
