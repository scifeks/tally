"""Docker adapter for triage agent image operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

from application.triage.container import (
    DockerNotAvailableError,
    TriageImageBuildError,
)


class DockerTriageImage:
    def image_exists(self, tag: str) -> bool:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", tag],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed or not on PATH")
        return result.returncode == 0

    def build_image(self, tag: str, context_dir: Path) -> None:
        try:
            result = subprocess.run(
                ["docker", "build", "-t", tag, str(context_dir)],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed or not on PATH")
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise TriageImageBuildError(
                f"Image build failed (exit {result.returncode}): {stderr[:500]}"
            )

    def remove_containers(self, image_tag: str) -> None:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"ancestor={image_tag}",
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise DockerNotAvailableError("Docker is not installed or not on PATH")
        container_ids = result.stdout.strip().split()
        for cid in container_ids:
            if cid:
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    capture_output=True,
                    text=True,
                )
