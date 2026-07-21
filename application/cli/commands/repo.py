"""Repository command handlers for the Tally CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError, resolve_project
from application.project.repositories_service import (
    DuplicateRepositoryName,
    ProjectRepositoriesService,
    RepositoryPathNotFound,
)
from core.config import Repository
from core.config.schemas.repo_service import RepoService

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def _split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _serialize_repo(repo: Repository) -> dict:
    """Auth credentials are never printed to stdout."""
    data = repo.model_dump()
    has_auth = repo.auth is not None and bool(repo.auth.login_url)
    data["auth_configured"] = has_auth
    data.pop("auth", None)
    data["id"] = repo.id
    return data


def _resolve(
    project_registry: ProjectRegistryService, project_name: str
) -> tuple[int, object]:
    try:
        return resolve_project(project_registry, project_name)
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        raise


def _find_repo_by_name(
    service: ProjectRepositoriesService,
    project_id: int,
    repo_name: str,
) -> Repository | None:
    repos = service.list_active(project_id)
    return next((r for r in repos if r.name == repo_name), None)


def _build_service_kwargs(args: Namespace) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"name": "default"}
    if args.languages:
        kwargs["languages"] = _split_csv(args.languages)
    if args.repo_type:
        kwargs["type"] = _split_csv(args.repo_type)
    if args.base_urls:
        kwargs["base_urls"] = _split_csv(args.base_urls)
    if args.graphql_paths:
        kwargs["graphql_paths"] = _split_csv(args.graphql_paths)
    if args.container_name:
        kwargs["container_name"] = args.container_name
    if args.docker_path:
        kwargs["docker_path"] = args.docker_path
    if args.dependencies_file:
        kwargs["dependencies_file"] = args.dependencies_file
    if args.test_dirs:
        kwargs["test_dirs"] = _split_csv(args.test_dirs)
    if args.ignore_dirs:
        kwargs["ignore_dirs"] = _split_csv(args.ignore_dirs)
    if args.no_crawl:
        kwargs["crawl_enabled"] = False
    return kwargs


def _parse_graphql_cop_headers(
    raw: str | None,
) -> dict[str, str] | None:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"Invalid --graphql-cop-headers JSON: {exc}",
            file=sys.stderr,
        )
        raise


def cmd_repo_add(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Add a repository to an existing project."""
    del tool_registry

    if not args.project or not args.repo_name or not args.repo_path:
        print(
            "Error: --project, --repo-name, and --repo-path are required",
            file=sys.stderr,
        )
        return INVALID_ARGS

    try:
        project_id, _ = _resolve(project_registry, args.project)
    except ProjectResolutionError:
        return PROJECT_NOT_FOUND

    repo_kwargs: dict[str, Any] = {
        "name": args.repo_name,
        "path": args.repo_path,
        "services": [RepoService(**_build_service_kwargs(args))],
    }
    if args.psalm_stubs:
        repo_kwargs["psalm_stubs"] = _split_csv(args.psalm_stubs)
    if args.graphql_cop_headers:
        try:
            headers = _parse_graphql_cop_headers(args.graphql_cop_headers)
            if headers is not None:
                repo_kwargs["graphql_cop_headers"] = headers
        except json.JSONDecodeError:
            return INVALID_ARGS

    try:
        repo = Repository(**repo_kwargs)
    except ValidationError as exc:
        print(
            f"Invalid repository configuration: {exc}",
            file=sys.stderr,
        )
        return INVALID_ARGS

    try:
        service = ProjectRepositoriesService.build(project_registry, str(base_path))
        created = service.create(project_id, repo)
    except RepositoryPathNotFound as exc:
        print(str(exc), file=sys.stderr)
        return INVALID_ARGS
    except DuplicateRepositoryName as exc:
        print(str(exc), file=sys.stderr)
        return INVALID_ARGS
    except ValidationError as exc:
        print(
            f"Invalid repository configuration: {exc}",
            file=sys.stderr,
        )
        return INVALID_ARGS
    except Exception as exc:
        print(f"Error creating repository: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    print(json.dumps(_serialize_repo(created), indent=2))
    return SUCCESS


def cmd_repo_list(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """List repositories for a project as JSON."""
    del tool_registry

    try:
        project_id, _ = _resolve(project_registry, args.project)
    except ProjectResolutionError:
        return PROJECT_NOT_FOUND

    try:
        service = ProjectRepositoriesService.build(project_registry, str(base_path))
        repos = service.list_active(project_id)
    except Exception as exc:
        print(f"Error listing repositories: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    print(json.dumps([_serialize_repo(r) for r in repos], indent=2))
    return SUCCESS


def cmd_repo_edit(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Patch fields on an existing repository."""
    del tool_registry

    if not args.project or not args.repo_name:
        print(
            "Error: --project and --repo-name are required",
            file=sys.stderr,
        )
        return INVALID_ARGS

    try:
        project_id, _ = _resolve(project_registry, args.project)
    except ProjectResolutionError:
        return PROJECT_NOT_FOUND

    try:
        service = ProjectRepositoriesService.build(project_registry, str(base_path))
    except Exception as exc:
        print(f"Error loading repositories: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    repo = _find_repo_by_name(service, project_id, args.repo_name)
    if repo is None:
        print(
            f"Error: Repository '{args.repo_name}' not found",
            file=sys.stderr,
        )
        return PROJECT_NOT_FOUND

    patch: dict[str, Any] = {}

    if args.repo_path is not None:
        patch["path"] = args.repo_path
    if args.psalm_stubs is not None:
        patch["psalm_stubs"] = _split_csv(args.psalm_stubs)
    if args.graphql_cop_headers is not None:
        try:
            headers = _parse_graphql_cop_headers(args.graphql_cop_headers)
            if headers is not None:
                patch["graphql_cop_headers"] = headers
        except json.JSONDecodeError:
            return INVALID_ARGS

    svc_patch: dict[str, Any] = {}
    if args.languages is not None:
        svc_patch["languages"] = _split_csv(args.languages)
    if args.repo_type is not None:
        svc_patch["type"] = _split_csv(args.repo_type)
    if args.base_urls is not None:
        svc_patch["base_urls"] = _split_csv(args.base_urls)
    if args.graphql_paths is not None:
        svc_patch["graphql_paths"] = _split_csv(args.graphql_paths)
    if args.container_name is not None:
        svc_patch["container_name"] = args.container_name
    if args.docker_path is not None:
        svc_patch["docker_path"] = args.docker_path
    if args.dependencies_file is not None:
        svc_patch["dependencies_file"] = args.dependencies_file
    if args.test_dirs is not None:
        svc_patch["test_dirs"] = _split_csv(args.test_dirs)
    if args.ignore_dirs is not None:
        svc_patch["ignore_dirs"] = _split_csv(args.ignore_dirs)
    if args.no_crawl:
        svc_patch["crawl_enabled"] = False

    if svc_patch:
        existing_svc = (
            repo.services[0].model_dump() if repo.services else {"name": "default"}
        )
        existing_svc.update(svc_patch)
        patch["services"] = [existing_svc]

    assert repo.id is not None
    try:
        updated = service.update(project_id, repo.id, patch)
    except ValidationError as exc:
        print(
            f"Invalid repository configuration: {exc}",
            file=sys.stderr,
        )
        return INVALID_ARGS
    except DuplicateRepositoryName as exc:
        print(str(exc), file=sys.stderr)
        return INVALID_ARGS
    except Exception as exc:
        print(f"Error updating repository: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    print(json.dumps(_serialize_repo(updated), indent=2))
    return SUCCESS


def cmd_repo_delete(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Soft-delete a repository."""
    del tool_registry

    if not args.project or not args.repo_name:
        print(
            "Error: --project and --repo-name are required",
            file=sys.stderr,
        )
        return INVALID_ARGS

    try:
        project_id, _ = _resolve(project_registry, args.project)
    except ProjectResolutionError:
        return PROJECT_NOT_FOUND

    try:
        service = ProjectRepositoriesService.build(project_registry, str(base_path))
    except Exception as exc:
        print(f"Error loading repositories: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    repo = _find_repo_by_name(service, project_id, args.repo_name)
    if repo is None:
        print(
            f"Error: Repository '{args.repo_name}' not found",
            file=sys.stderr,
        )
        return PROJECT_NOT_FOUND

    assert repo.id is not None
    try:
        service.delete(project_id, repo.id)
    except Exception as exc:
        print(f"Error deleting repository: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    return SUCCESS
