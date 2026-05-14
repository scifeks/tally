"""File-based adapter for global tool commands configuration."""

from __future__ import annotations

import json
from pathlib import Path

from application.ports.global_commands import GlobalCommandsPort


class GlobalCommandsRepository(GlobalCommandsPort):
    """Read/write global tool commands from JSON file."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def load_all(self) -> dict[str, dict]:
        """Load commands from JSON file; empty dict if not present."""
        if not self._config_path.exists():
            return {}
        with open(self._config_path) as f:
            return json.load(f)

    def save_all(self, commands: dict[str, dict]) -> None:
        """Save commands to JSON file; create parent directory if needed."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w") as f:
            json.dump(commands, f, indent=2)
