"""Triage command handler for the Tally CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    RATE_LIMITED,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError, resolve_project
from application.locking import JobBusy
from application.mcp.token_minting import mint_bearer_token
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
from core.config import ConfigManager
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

    if args.resume is not None:
        return _cmd_triage_resume(args, project_registry, tool_registry, base_path)

    if args.interaction_mode or args.billing_method or args.api_key_override:
        return _cmd_triage_with_mode(args, project_registry, tool_registry, base_path)

    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    config = ConfigManager(str(base_path))
    gcfg = config.global_config
    triage_provider = ""
    triage_api_key = ""
    if gcfg.triage_inference:
        triage_provider = gcfg.triage_inference.provider
        if triage_provider in ("claude", "claude_code"):
            triage_api_key = gcfg.claude.api_key if gcfg.claude else ""
        elif triage_provider == "openai":
            triage_api_key = gcfg.openai.api_key if gcfg.openai else ""

    readiness = compute_triage_readiness(
        provider=triage_provider,
        docker_available=RuntimeDependencyService(
            build_runtime_dependency_probes(base_path=str(base_path))
        ).is_installed("docker"),
        api_key=triage_api_key,
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


def _cmd_triage_resume(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Resume a paused triage run."""
    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return PROJECT_NOT_FOUND

    interaction_mode: Literal["interactive", "background"] | None = cast(
        Literal["interactive", "background"] | None,
        args.interaction_mode,
    )
    if interaction_mode is None:
        interaction_mode = _infer_triage_mode(str(base_path), project_name, args.resume)

    if interaction_mode == "interactive" and args.billing_method:
        print(
            "Error: --billing-method requires --interaction-mode background",
            file=sys.stderr,
        )
        return INVALID_ARGS

    readiness = compute_triage_readiness(
        provider="",
        docker_available=RuntimeDependencyService(
            build_runtime_dependency_probes(base_path=str(base_path))
        ).is_installed("docker"),
        api_key="",
    )
    if not readiness.enabled:
        print(f"Error: {readiness.reason}", file=sys.stderr)
        return GENERAL_ERROR

    repos = load_active_repos(str(base_path), project_name)
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}

    if interaction_mode == "interactive":
        try:
            ensure_triage_image(base_path)
        except DockerNotAvailableError:
            print("Error: Docker is not installed or not running.", file=sys.stderr)
            return GENERAL_ERROR
        except TriageImageBuildError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return GENERAL_ERROR

        try:
            ensure_triage_containers(base_path, project_name, repo_paths=repo_paths)
        except DockerNotAvailableError:
            print("Error: Docker is not installed or not running.", file=sys.stderr)
            return GENERAL_ERROR
        except (ComposeGenerationError, TriageContainerStartError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return GENERAL_ERROR

    try:
        service = create_triage_service(
            project_registry,
            project_id,
            repo_paths=repo_paths,
        )
    except ProjectNotFound:
        print(f"Error: project {project_name!r} not found", file=sys.stderr)
        return PROJECT_NOT_FOUND

    try:
        handle = service.resume_triage(
            base_path=str(base_path),
            project_id=project_id,
            project_name=project_name,
            scan_run_id=args.resume,
            tool_registry=tool_registry,
            event_sink=NullTriageEventSink(),
            interaction_mode=interaction_mode,
            billing_method=cast(
                Literal["plan", "api"] | None,
                args.billing_method,
            ),
            api_key=args.api_key_override,
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
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    if interaction_mode == "interactive":
        _print_interactive_triage_info(str(base_path), args.resume)

    result = handle.result.result()

    if result.get("status") == "rate_limited":
        print(
            f"Triage paused: rate limited after {result['sessions_run']} session(s). "
            "Resume with: tally --command triage --resume <scan_run_id>",
            file=sys.stderr,
        )
        return RATE_LIMITED

    print(
        f"Triage: {result['sessions_run']} sessions run, "
        f"{result['success']} success, "
        f"{result['failed']} failed, "
        f"{result['incomplete']} incomplete"
    )
    return SUCCESS


def _cmd_triage_with_mode(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Start triage with mode flags."""
    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return PROJECT_NOT_FOUND

    interaction_mode: Literal["interactive", "background"] = cast(
        Literal["interactive", "background"],
        args.interaction_mode or "interactive",
    )

    if interaction_mode == "interactive" and args.billing_method:
        print(
            "Error: --billing-method requires --interaction-mode background",
            file=sys.stderr,
        )
        return INVALID_ARGS

    readiness = compute_triage_readiness(
        provider="",
        docker_available=RuntimeDependencyService(
            build_runtime_dependency_probes(base_path=str(base_path))
        ).is_installed("docker"),
        api_key="",
    )
    if not readiness.enabled:
        print(f"Error: {readiness.reason}", file=sys.stderr)
        return GENERAL_ERROR

    repos = load_active_repos(str(base_path), project_name)
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}

    if interaction_mode == "interactive":
        try:
            ensure_triage_image(base_path)
        except DockerNotAvailableError:
            print("Error: Docker is not installed or not running.", file=sys.stderr)
            return GENERAL_ERROR
        except TriageImageBuildError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return GENERAL_ERROR

        try:
            ensure_triage_containers(base_path, project_name, repo_paths=repo_paths)
        except DockerNotAvailableError:
            print("Error: Docker is not installed or not running.", file=sys.stderr)
            return GENERAL_ERROR
        except (ComposeGenerationError, TriageContainerStartError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return GENERAL_ERROR

    try:
        service = create_triage_service(
            project_registry,
            project_id,
            repo_paths=repo_paths,
        )
    except ProjectNotFound:
        print(f"Error: project {project_name!r} not found", file=sys.stderr)
        return PROJECT_NOT_FOUND

    try:
        handle = service.start_triage(
            base_path=str(base_path),
            project_id=project_id,
            project_name=project_name,
            tool_registry=tool_registry,
            event_sink=NullTriageEventSink(),
            interaction_mode=interaction_mode,
            billing_method=cast(
                Literal["plan", "api"] | None,
                args.billing_method,
            ),
            api_key=args.api_key_override,
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
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    if interaction_mode == "interactive":
        _print_interactive_triage_info(str(base_path), handle.scan_run_id)

    result = handle.result.result()

    if result.get("status") == "rate_limited":
        print(
            f"Triage paused: rate limited after {result['sessions_run']} session(s). "
            "Resume with: tally --command triage --resume <scan_run_id>",
            file=sys.stderr,
        )
        return RATE_LIMITED

    print(
        f"Triage: {result['sessions_run']} sessions run, "
        f"{result['success']} success, "
        f"{result['failed']} failed, "
        f"{result['incomplete']} incomplete"
    )
    return SUCCESS


def _print_interactive_triage_info(base_path: str, scan_run_id: int) -> None:
    """Print MCP connection info for interactive triage."""
    token = mint_bearer_token(
        f"triage-interactive-{scan_run_id}",
        base_path=Path(base_path),
    )
    cfg = ConfigManager(base_path).global_config
    mcp_url = f"http://{cfg.mcp.host}:{cfg.mcp.port}/mcp"

    print("Interactive triage ready.")
    print("Use the connection info below in your Claude Code session.\n")
    print(f"  mcp_url:          {mcp_url}")
    print(f"  mcp_bearer_token: {token}")
    print(f"  scan_run_id:      {scan_run_id}")


def _infer_triage_mode(
    base_path: str, project_name: str, run_id: int
) -> Literal["interactive", "background"]:
    """Infer the original interaction mode from triage execution history.

    A usage_pool value of plan/api means background. Falls back to
    'interactive' when no execution data exists (the historical default
    for triage resume).
    """
    _, _, triage_repo, _ = make_store(base_path, project_name)
    pool = triage_repo.get_latest_usage_pool(run_id)
    if pool in ("plan", "api"):
        return "background"
    return "interactive"


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
    repos = load_active_repos(str(base_path), project_name)
    repo_paths = {r.name: Path(r.path) for r in repos if r.path}

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
        ensure_triage_containers(Path(base_path), project_name, repo_paths=repo_paths)
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
        service = create_triage_service(
            project_registry,
            project_id,
            repo_paths=repo_paths,
        )
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

    if result.get("status") == "rate_limited":
        print(
            f"Triage paused: rate limited after {result['sessions_run']} session(s). "
            "Resume with: tally triage --resume",
            file=sys.stderr,
        )
        # exit 4 (RATE_LIMITED): distinct from success (0) and generic failure (1)
        return RATE_LIMITED

    print(
        f"Triage: {result['sessions_run']} sessions run, "
        f"{result['success']} success, "
        f"{result['failed']} failed, "
        f"{result['incomplete']} incomplete"
    )
    return SUCCESS
