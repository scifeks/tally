"""Port for agent sandbox Docker Compose file operations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentComposePort(Protocol):
    def write_compose_file(self, content: str, compose_path: Path) -> None: ...
