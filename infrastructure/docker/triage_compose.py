"""Docker adapter for triage agent Compose file operations."""

from __future__ import annotations

from pathlib import Path


class DockerTriageCompose:
    def write_compose_file(self, content: str, compose_path: Path) -> None:
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        compose_path.write_text(content)
