"""Docker wrapper for pip-audit Python dependency vulnerability scanning."""

import logging
import subprocess

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.wrappers.base.pip_audit import BasePipAuditTool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec
from infrastructure.tools.wrappers.utils.pip_deps import find_or_generate_requirements

logger = logging.getLogger(__name__)


def _container_file_exists(container_name: str, path: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", "exec", container_name, "test", "-f", path],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except Exception as exc:
        logger.debug("pip-audit: container file check failed: %s", exc)
        return False


def _resolve_and_copy_deps(
    local_repo_path: str,
    container_name: str,
    dest_path: str,
) -> str | None:
    """Resolve a pip-audit-compatible requirements file from the local repo
    and copy it into the container at dest_path.

    Delegates format detection and lock-file export to
    find_or_generate_requirements, which handles requirements.txt,
    poetry.lock, Pipfile.lock, pyproject.toml, setup.py, uv.lock, etc.

    Returns dest_path on success, None if nothing could be resolved or
    the docker cp fails.
    """
    if not local_repo_path:
        return None
    local_req = find_or_generate_requirements(local_repo_path)
    if not local_req:
        return None
    try:
        r = subprocess.run(
            ["docker", "cp", local_req, f"{container_name}:{dest_path}"],
            capture_output=True,
            timeout=30,
        )
        if r.returncode == 0:
            logger.info(
                "pip-audit: copied %r to %r in container %r",
                local_req,
                dest_path,
                container_name,
            )
            return dest_path
        logger.warning(
            "pip-audit: docker cp failed (rc=%d): %s",
            r.returncode,
            r.stderr.decode(errors="replace"),
        )
        return None
    except Exception as exc:
        logger.warning("pip-audit: docker cp raised: %s", exc)
        return None


def _install_pip_audit_in_container(container_name: str) -> bool:
    """Install pip-audit inside the container. Returns True on success."""
    logger.info("pip-audit: not found in container %r — installing...", container_name)
    try:
        r = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "pip",
                "install",
                "--quiet",
                "pip-audit",
            ],
            capture_output=True,
            timeout=120,
        )
        if r.returncode == 0:
            logger.info(
                "pip-audit: installed successfully in container %r",
                container_name,
            )
            return True
        logger.warning(
            "pip-audit: install in container %r failed (rc=%d): %s",
            container_name,
            r.returncode,
            r.stderr.decode(errors="replace"),
        )
        return False
    except Exception as exc:
        logger.warning("pip-audit: container install raised: %s", exc)
        return False


class PipAuditDockerTool(BasePipAuditTool):
    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        """Return True if pip-audit exists in the container, installing if needed."""
        if _container_file_exists(self._container_name, self._tool_path):
            return True
        return _install_pip_audit_in_container(self._container_name)

    def get_version(self) -> str | None:
        return None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo = context.repo
        repo_path = context.registry.get_repo_path(self.name, repo)
        deps_file = repo.dependencies_file

        # If a dependencies_file is configured but absent from the container,
        # attempt to copy the local requirements.txt into the container.
        if deps_file and not _container_file_exists(self._container_name, deps_file):
            deps_file = _resolve_and_copy_deps(
                repo.path, self._container_name, deps_file
            )
            if deps_file is None:
                logger.info(
                    "pip-audit: no requirements file available for %r — skipping",
                    repo.name,
                )
                return []

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs={
                    "repo_path": repo_path,
                    "dependencies_file": deps_file,
                },
            )
        ]

    def build_command(self, **kwargs) -> list[str]:
        """Build docker exec argv for pip-audit.

        When ``dependencies_file`` is set, scopes the scan to the declared
        dependencies via ``-r <dependencies_file>``.  When absent, runs
        pip-audit with no ``-r`` flag, scanning all packages installed in
        the container environment.

        Keyword Args:
            repo_path (str): Container path to the repository (docker_path).
            dependencies_file (str): Container path to the dependencies file,
                or empty string for a full environment scan.
        """
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'edit-repo' to set the container mount path."
            )
        dependencies_file: str = kwargs.get("dependencies_file", "")
        tool_args = ["--format", "json"]
        if dependencies_file:
            tool_args.extend(["-r", dependencies_file])
        return build_docker_exec(
            self._container_name, self._tool_path, tool_args, workdir=repo_path
        )
