"""Triage agent Docker image management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.triage_image import TriageImagePort

TRIAGE_IMAGE_TAG = "tally/triage-agent"


class DockerNotAvailableError(RuntimeError):
    """Docker is not installed or the daemon is not running."""


class TriageImageBuildError(RuntimeError):
    """The triage agent Docker image failed to build."""


def _resolve_image_port() -> TriageImagePort:
    from infrastructure.docker.triage_image import DockerTriageImage

    return DockerTriageImage()


def triage_image_ready() -> bool:
    """Returns True if the triage agent image exists locally."""
    return _resolve_image_port().image_exists(TRIAGE_IMAGE_TAG)


def build_triage_image(app_root: Path) -> None:
    """Builds the triage agent image from the Dockerfile."""
    context_dir = app_root / "docker" / "triage-agent"
    if not (context_dir / "Dockerfile").is_file():
        raise FileNotFoundError(f"Dockerfile not found at {context_dir / 'Dockerfile'}")
    _resolve_image_port().build_image(TRIAGE_IMAGE_TAG, context_dir)


def ensure_triage_image(app_root: Path) -> bool:
    """Checks image; builds if missing. Returns True if a build ran."""
    if triage_image_ready():
        return False
    build_triage_image(app_root)
    return True


def rebuild_triage_image(app_root: Path) -> None:
    """Removes running containers and rebuilds the image."""
    _resolve_image_port().remove_containers(TRIAGE_IMAGE_TAG)
    build_triage_image(app_root)
