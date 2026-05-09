"""Triage agent Docker image and container lifecycle."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.triage_container import (
        TriageContainerPort,
    )
    from application.ports.triage_image import TriageImagePort

TRIAGE_IMAGE_TAG = "tally/triage-agent"

log = logging.getLogger(__name__)


class DockerNotAvailableError(RuntimeError):
    """Docker is not installed or the daemon is not running."""


class TriageImageBuildError(RuntimeError):
    """The triage agent Docker image failed to build."""


class TriageContainerStartError(RuntimeError):
    """Triage compose services failed to start."""


# -- image lifecycle --


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


# -- compose service lifecycle --


def _resolve_container_port() -> TriageContainerPort:
    from infrastructure.docker.triage_container import (
        DockerTriageContainer,
    )

    return DockerTriageContainer()


def _compose_path(app_root: Path) -> Path:
    from application.triage.compose import COMPOSE_RELATIVE_PATH

    return app_root / COMPOSE_RELATIVE_PATH


def triage_containers_running(app_root: Path) -> bool:
    """Returns True if triage compose services are running."""
    return _resolve_container_port().is_running(_compose_path(app_root))


def ensure_triage_containers(app_root: Path, project: str) -> bool:
    """Generates compose and starts services if not running.

    Returns True if services were started, False if already running.
    """
    path = _compose_path(app_root)
    port = _resolve_container_port()

    if port.is_running(path):
        return False

    from application.triage.compose import generate_triage_compose
    from application.triage.factory import resolve_triage_config
    from core.project_paths import ProjectPaths
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.repositories import (
        RepositoryRepository,
    )

    resolved = resolve_triage_config(app_root=app_root)
    paths = ProjectPaths.from_canonical(app_root, project)
    factory = ConnectionFactory(paths.findings_db)
    repos = RepositoryRepository(factory).list_active()
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}

    generate_triage_compose(
        app_root,
        repo_paths,
        provider=resolved.provider_name,
        base_url=resolved.base_url,
        model=resolved.model,
    )
    port.up(path)
    return True


def teardown_triage_containers(app_root: Path) -> None:
    """Brings compose services down (best-effort, swallows errors)."""
    try:
        path = _compose_path(app_root)
        if not path.is_file():
            return
        _resolve_container_port().down(path)
    except Exception:
        log.debug("Container teardown failed", exc_info=True)
