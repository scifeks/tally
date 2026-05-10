"""Port for triage agent Docker Compose service lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TriageContainerPort(Protocol):
    def is_running(self, compose_path: Path) -> bool: ...

    def up(self, compose_path: Path) -> None: ...

    def down(self, compose_path: Path) -> None: ...
