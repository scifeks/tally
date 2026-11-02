"""Agent sandbox Docker image lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.agent_image import AgentImagePort

AGENT_IMAGE_TAG = "tally/triage-agent"


class DockerNotAvailableError(RuntimeError):
    """Docker is not installed or the daemon is not running."""


class AgentImageBuildError(RuntimeError):
    """The agent sandbox Docker image failed to build."""


def _resolve_image_port() -> AgentImagePort:
    from infrastructure.docker.agent_image import DockerAgentImage

    return DockerAgentImage()


def image_ready() -> bool:
    """Returns True if the agent sandbox image exists locally."""
    return _resolve_image_port().image_exists(AGENT_IMAGE_TAG)


def build_image(app_root: Path) -> None:
    """Builds the agent sandbox image from the Dockerfile."""
    context_dir = app_root / "docker" / "triage-agent"
    if not (context_dir / "Dockerfile").is_file():
        raise FileNotFoundError(f"Dockerfile not found at {context_dir / 'Dockerfile'}")
    _resolve_image_port().build_image(AGENT_IMAGE_TAG, context_dir)


def ensure_image(app_root: Path) -> bool:
    """Checks image; builds if missing. Returns True if a build ran."""
    if image_ready():
        return False
    build_image(app_root)
    return True


def rebuild_image(app_root: Path) -> None:
    """Removes running containers and rebuilds the image."""
    _resolve_image_port().remove_containers(AGENT_IMAGE_TAG)
    build_image(app_root)
