"""Docker Compose adapter for triage agent service lifecycle."""

from __future__ import annotations

import subprocess
from pathlib import Path

from application.triage.container import (
    DockerNotAvailableError,
    TriageContainerStartError,
)


class DockerTriageContainer:
    def is_running(self, compose_path: Path) -> bool:
        if not compose_path.is_file():
            return False
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_path),
                    "ps",
                    "--status",
                    "running",
                    "-q",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed or not on PATH")
        return bool(result.stdout.strip())

    def up(self, compose_path: Path) -> None:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_path),
                    "up",
                    "-d",
                    "--wait",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed or not on PATH")
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise TriageContainerStartError(
                f"Container start failed (exit {result.returncode}): {stderr[:500]}"
            )

    def down(self, compose_path: Path) -> None:
        try:
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_path),
                    "down",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed or not on PATH")
