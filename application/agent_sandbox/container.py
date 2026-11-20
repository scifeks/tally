"""Agent sandbox Docker container lifecycle."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.agent_container import AgentContainerPort

log = logging.getLogger(__name__)


class AgentContainerStartError(RuntimeError):
    """Agent sandbox compose services failed to start."""


def _resolve_container_port() -> AgentContainerPort:
    from infrastructure.docker.agent_container import DockerAgentContainer

    return DockerAgentContainer()


def _compose_path(app_root: Path) -> Path:
    from application.agent_sandbox.compose import COMPOSE_RELATIVE_PATH

    return app_root / COMPOSE_RELATIVE_PATH


def containers_running(app_root: Path) -> bool:
    """Returns True if agent sandbox compose services are running."""
    return _resolve_container_port().is_running(_compose_path(app_root))


def ensure_containers(
    app_root: Path,
    *,
    provider: str,
    base_url: str = "",
    model: str = "",
    repo_paths: dict[str, Path] | None = None,
) -> bool:
    """Generate compose and start services for the given provider.

    Always regenerates the compose file so volume mounts reflect the
    current ``repo_paths``. If containers are already running and the
    compose file changed, tears them down and restarts. Returns True
    if services were (re)started.

    ``base_url`` and ``model`` are only read for OpenCode providers;
    the Claude and Claude SDK providers ignore them.
    """
    from application.agent_sandbox.compose import generate_compose

    path = _compose_path(app_root)
    port = _resolve_container_port()

    old_content = path.read_text() if path.is_file() else ""

    generate_compose(
        app_root,
        repo_paths or {},
        provider=provider,
        base_url=base_url,
        model=model,
    )

    new_content = path.read_text()
    running = port.is_running(path)

    if running and new_content == old_content:
        return False

    if running:
        log.info("Compose changed; restarting agent sandbox containers")
        port.down(path)

    port.up(path)
    return True


def teardown_containers(app_root: Path) -> None:
    """Brings compose services down (best-effort, swallows errors)."""
    try:
        path = _compose_path(app_root)
        if not path.is_file():
            return
        _resolve_container_port().down(path)
    except Exception:
        log.debug("Container teardown failed", exc_info=True)
