"""Triage command handler for the Tally CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.exit_codes import GENERAL_ERROR, PROJECT_NOT_FOUND, SUCCESS
from application.cli.project import ProjectResolutionError, resolve_project
from application.locking import JobBusy
from application.ports.triage_event_sink import NullTriageEventSink
from application.runtime import (
    RuntimeDependencyService,
    build_runtime_dependency_probes,
)
from application.triage.compose import ComposeGenerationError
from application.triage.container import (
    DockerNotAvailableError,
    TriageContainerStartError,
    TriageImageBuildError,
    ensure_triage_containers,
    ensure_triage_image,
    rebuild_triage_image,
    teardown_triage_containers,
)
from application.triage.orchestrator import (
    run_triage_batch_only,
    run_triage_dry_run,
)
from application.triage.readiness import compute_triage_readiness
from application.triage.runner import NoScanRunError
from factories.persistence import (
    ProjectNotFound,
    create_triage_service,
    load_active_repos,
    make_store,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_triage(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Run triage in the requested mode and return an exit code."""
    if args.rebuild_container:
        return _rebuild_container(base_path)

    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    readiness = compute_triage_readiness(
        base_path=str(base_path),
        docker_available=RuntimeDependencyService(
            build_runtime_dependency_probes(base_path=str(base_path))
        ).is_installed("docker"),
    )
    if not readiness.enabled:
        print(f"Error: {readiness.reason}", file=sys.stderr)
        return GENERAL_ERROR

    if args.batch:
        return _batch_mode(tool_registry, base_path, project_name)

    if args.dry_run:
        return _dry_run_mode(tool_registry, base_path, project_name)

    return _full_triage_mode(
        project_id,
        project_registry,
        tool_registry,
        base_path,
        project_name,
    )


def _rebuild_container(base_path: Path) -> int:
    """Tear down containers and rebuild the triage agent image."""
    app_root = Path(base_path)
    print("Stopping triage agent containers...")
    try:
        teardown_triage_containers(app_root)
        rebuild_triage_image(app_root)
    except DockerNotAvailableError:
        print(
            "Error: Docker is not installed or not running.",
            file=sys.stderr,
        )
        return GENERAL_ERROR
    except (TriageImageBuildError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    print("Triage agent image rebuilt.")
    return SUCCESS


def _batch_mode(
    tool_registry: ToolRegistry,
    base_path: Path,
    project_name: str,
) -> int:
    """Create triage batches without invoking the agent."""
    run_repo, finding_repo, triage_repo, audit_repo = make_store(
        str(base_path), project_name
    )
    repos = load_active_repos(str(base_path), project_name)
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}
    count = run_triage_batch_only(
        project_name,
        tool_registry,
        app_root=Path(base_path),
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    print(f"Created {count} batches")
    return SUCCESS


def _dry_run_mode(
    tool_registry: ToolRegistry,
    base_path: Path,
    project_name: str,
) -> int:
    """Render triage batch prompts to the debug log without executing."""
    run_repo, finding_repo, triage_repo, audit_repo = make_store(
        str(base_path), project_name
    )
    repos = load_active_repos(str(base_path), project_name)
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}
    count = run_triage_dry_run(
        project_name,
        tool_registry,
        app_root=Path(base_path),
        run_repo=run_repo,
        finding_repo=finding_repo,
        triage_repo=triage_repo,
        audit_repo=audit_repo,
        repo_paths=repo_paths,
    )
    print(f"Rendered {count} batch prompt(s); see DEBUG log")
    return SUCCESS


def _full_triage_mode(
    project_id: int,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
    project_name: str,
) -> int:
    """Run full triage with Docker containers."""
    try:
        ensure_triage_image(Path(base_path))
    except DockerNotAvailableError:
        print(
            "Error: Docker is not installed or not running.",
            file=sys.stderr,
        )
        return GENERAL_ERROR
    except TriageImageBuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    try:
        ensure_triage_containers(Path(base_path), project_name)
    except DockerNotAvailableError:
        print(
            "Error: Docker is not installed or not running.",
            file=sys.stderr,
        )
        return GENERAL_ERROR
    except (ComposeGenerationError, TriageContainerStartError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    try:
        service = create_triage_service(project_registry, project_id)
    except ProjectNotFound:
        print(
            f"Error: project {project_name!r} not found",
            file=sys.stderr,
        )
        return PROJECT_NOT_FOUND

    try:
        handle = service.start_triage(
            base_path=str(base_path),
            project_id=project_id,
            project_name=project_name,
            tool_registry=tool_registry,
            event_sink=NullTriageEventSink(),
        )
    except NoScanRunError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR
    except JobBusy as exc:
        print(
            f"Another triage is in progress (holder={exc.current_holder}).",
            file=sys.stderr,
        )
        return GENERAL_ERROR

    result = handle.result.result()
    print(
        f"Triage: {result['sessions_run']} sessions run, "
        f"{result['success']} success, "
        f"{result['failed']} failed, "
        f"{result['incomplete']} incomplete"
    )
    return SUCCESS
