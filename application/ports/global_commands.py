"""Persistence port for global tool commands configuration."""

from __future__ import annotations

from typing import Protocol


class GlobalCommandsPort(Protocol):
    """Interface for loading and saving global tool commands."""

    def load_all(self) -> dict[str, dict]: ...
    def save_all(self, commands: dict[str, dict]) -> None: ...
