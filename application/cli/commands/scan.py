"""Scan command handler for the Tally CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.adapters import CliProgressReporter, CliPromptAdapter
from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError, resolve_project
from application.locking.exceptions import JobBusy
from application.project.repositories_service import ProjectRepositoriesService
from application.tools.orchestrator import ScanCancelled
from application.tools.scan_service import get_scan_service
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from factories.persistence import (
    create_finding_repo,
    create_overrides_repo,
    create_repo_repo,
    create_scan_repos,
    create_url_finding_repo,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_scan(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Run a scan and return an exit code."""
    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    paths = ProjectPaths.from_canonical(base_path, project_name)
    overrides_repo = create_overrides_repo(paths.findings_db)

    from application.tools.registry import discover_tools

    discover_tools(
        tool_registry,
        str(base_path),
        project_name=project_name,
        overrides_repo=overrides_repo,
    )
    try:
        return _cmd_scan_inner(
            args,
            project_registry,
            tool_registry,
            base_path,
            project_id,
            project_name,
        )
    finally:
        discover_tools(tool_registry, str(base_path))


def _cmd_scan_inner(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
    project_id: int,
    project_name: str,
) -> int:
    """Validate args and dispatch the scan after registry refresh."""
    from application.rag.ingestor import get_tool_domain
    from domain.tools.constants import DOMAINS

    skip_enrichment = args.skip_enrichment

    repo_val: str | None = args.repo
    tool_val: str | None = args.tool
    domain_val: str | None = args.domain
    skip_tools_val: str | None = args.skip_tools

    repo_names: list[str] | None = None
    if repo_val is not None:
        requested_repos = [r.strip() for r in repo_val.split(",") if r.strip()]
        config = ConfigManager(str(base_path))
        service = ProjectRepositoriesService(project_registry, config)
        active_repos = service.list_active(project_id)
        repo_map = {r.name.lower(): r.name for r in active_repos}
        invalid_repos = [r for r in requested_repos if r.lower() not in repo_map]
        if invalid_repos:
            names = sorted(repo_map.values())
            repo_list = ", ".join(names) if names else "none"
            print(
                f"Unknown repository: {', '.join(invalid_repos)}\n"
                f"Configured repos: {repo_list}",
                file=sys.stderr,
            )
            return INVALID_ARGS
        repo_names = [repo_map[r.lower()] for r in requested_repos]

    requested_tools: list[str] | None = None
    if tool_val is not None:
        requested_tools = [t.strip() for t in tool_val.split(",") if t.strip()]
        known = set(tool_registry.list_tool_names())
        invalid = [t for t in requested_tools if t not in known]
        if invalid:
            print(
                f"Unknown tool(s): {', '.join(invalid)}\n"
                f"Configured tools: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return INVALID_ARGS

    requested_domains: list[str] | None = None
    if domain_val is not None:
        requested_domains = [t.strip() for t in domain_val.split(",") if t.strip()]
        invalid_d = [t for t in requested_domains if t not in DOMAINS]
        if invalid_d:
            print(
                f"Unknown domain(s): {', '.join(invalid_d)}\n"
                f"Valid domains: {', '.join(sorted(DOMAINS))}",
                file=sys.stderr,
            )
            return INVALID_ARGS

    skip_tools: set[str] = set()
    if skip_tools_val is not None:
        parsed_skips = [t.strip() for t in skip_tools_val.split(",") if t.strip()]
        known = set(tool_registry.list_tool_names())
        invalid_skips = [t for t in parsed_skips if t not in known]
        if invalid_skips:
            print(
                f"Unknown tool(s): {', '.join(invalid_skips)}\n"
                f"Configured tools: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return INVALID_ARGS
        skip_tools = set(parsed_skips)

    effective_tools: list[str] | None = None
    if requested_tools is not None or requested_domains is not None:
        all_configured = list(tool_registry.list_tool_names())
        candidates = (
            list(requested_tools) if requested_tools is not None else all_configured
        )
        if requested_domains is not None:
            candidates = [
                t for t in candidates if get_tool_domain(t) in requested_domains
            ]
        effective_tools = candidates

    paths = ProjectPaths.from_canonical(base_path, project_name)
    run_repo, chat_repo, profiles_repo, _ = create_scan_repos(paths.findings_db)

    finding_repo = create_finding_repo(paths.findings_db)
    repo_repo = create_repo_repo(paths.findings_db)
    url_finding_repo = create_url_finding_repo(paths.findings_db)

    from application.cli.display import CliDisplay
    from application.ports.scan_event_sink import NullScanEventSink

    try:
        handle = get_scan_service().start_scan(
            project_id=project_id,
            project_name=project_name,
            base_path=str(base_path),
            tool_registry=tool_registry,
            run_repo=run_repo,
            chat_session_repo=chat_repo,
            profiles_repo=profiles_repo,
            finding_repo=finding_repo,
            repo_repo=repo_repo,
            url_finding_repo=url_finding_repo,
            repo_ids=tuple(repo_names or ()),
            tool_ids=tuple(effective_tools or ()),
            skip_tool_ids=tuple(skip_tools),
            skip_enrichment=skip_enrichment,
            prompt=CliPromptAdapter(),
            reporter=CliProgressReporter(),
            display=CliDisplay(),
            event_sink=NullScanEventSink(),
            run_args={"args": []},
        )
    except JobBusy as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    try:
        handle.result.result()
    except ScanCancelled:
        print("Scan cancelled.", file=sys.stderr)
        return GENERAL_ERROR
    except Exception as exc:
        print(f"Scan failed: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    return SUCCESS
