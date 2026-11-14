"""Scanning factory functions for composition root wiring."""

from __future__ import annotations

from application.ports.git_diff import GitDiffPort
from application.ports.subprocess_runner import SubprocessRunnerPort
from application.tools.scan_service import ScanService
from domain.runtime.probe import RuntimeDependencyProbe
from infrastructure.tools.cli_runner import CliToolRunner
from infrastructure.tools.runner import SubprocessRunner
from infrastructure.vcs.git_diff_adapter import GitDiffAdapter


def create_subprocess_runner() -> SubprocessRunnerPort:
    """Construct a subprocess runner."""
    return SubprocessRunner()


def create_git_diff() -> GitDiffPort:
    """Construct a git diff adapter."""
    return GitDiffAdapter(SubprocessRunner())


_SERVICE: ScanService | None = None


def get_scan_service() -> ScanService:
    """Return the process-shared ScanService singleton."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ScanService(
            cli_tool_runner=CliToolRunner(SubprocessRunner()),
        )
    return _SERVICE


def get_manifest_constants() -> dict[str, list[str]]:
    from infrastructure.tools.wrappers.utils.manifest_check import (
        LANGUAGE_MANIFESTS,
    )

    return LANGUAGE_MANIFESTS


def check_dependency_manifests(
    repo_path: str,
    languages: list[str],
) -> bool:
    from infrastructure.tools.wrappers.utils.manifest_check import (
        has_dependency_manifests,
    )

    return has_dependency_manifests(repo_path, languages)


def check_dependency_manifests_docker(
    container_name: str,
    repo_path: str,
    languages: list[str],
) -> bool:
    from infrastructure.tools.wrappers.utils.manifest_check import (
        has_dependency_manifests_docker,
    )

    return has_dependency_manifests_docker(container_name, repo_path, languages)


def check_manifests_for_language(
    repo_path: str,
    language: str,
    container_name: str = "",
) -> bool:
    from infrastructure.tools.wrappers.utils.manifest_check import (
        has_manifests_for_language,
    )

    return has_manifests_for_language(repo_path, language, container_name)


def probe_container_tools(
    container_name: str,
    languages: list[str],
) -> dict[str, str]:
    from infrastructure.tools.wrappers.utils.container_tool_probe import (
        probe_container_tools as _probe,
    )

    return _probe(container_name, languages)


def build_docker_exec(
    container_name: str,
    tool_path: str,
    tool_args: list[str],
    workdir: str | None = None,
) -> list[str]:
    from infrastructure.tools.wrappers.docker._docker_exec import (
        build_docker_exec as _build,
    )

    return _build(container_name, tool_path, tool_args, workdir=workdir)


def reset_scan_scoped_state() -> None:
    from infrastructure.tools.wrappers.utils.scan_state import (
        reset_scan_scoped_state as _reset,
    )

    _reset()


def create_docker_probe() -> RuntimeDependencyProbe:
    from infrastructure.runtime.docker_probe import DockerProbe

    return DockerProbe()
