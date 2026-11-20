"""Port for agent sandbox Docker image operations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentImagePort(Protocol):
    def image_exists(self, tag: str) -> bool: ...

    def build_image(self, tag: str, context_dir: Path) -> None: ...

    def remove_containers(self, image_tag: str) -> None: ...
