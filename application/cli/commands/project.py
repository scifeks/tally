"""Project command handlers for the Tally CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    SUCCESS,
)
from application.project.manager import ProjectManager
from core.project_paths import ProjectPaths
from factories.persistence import init_project_schema

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_project_create(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Create a new project and return an exit code."""
    del tool_registry

    name = getattr(args, "project", None)
    if not name:
        print("Error: project name is required", file=sys.stderr)
        return INVALID_ARGS

    try:
        existing = project_registry.resolve_by_name(name)
        if existing is not None and existing.archived_at is None:
            print(
                f"Error: project '{name}' already exists",
                file=sys.stderr,
            )
            return GENERAL_ERROR
    except Exception as exc:
        print(f"Error checking project: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    try:
        manager = ProjectManager(str(base_path), registry=project_registry)
        manager.create_project_dirs(name)
        manager.save_project(
            name,
            company_name=getattr(args, "company_name", ""),
            department_name=getattr(args, "department_name", ""),
            abbreviation=getattr(args, "abbreviation", ""),
        )

        paths = ProjectPaths.from_canonical(base_path, name)
        init_project_schema(paths.findings_db)

        row = project_registry.resolve_by_name(name)
        if row is None:
            print(
                "Error: could not resolve created project",
                file=sys.stderr,
            )
            return GENERAL_ERROR

        print(json.dumps({"id": row.id, "name": name}))
        return SUCCESS

    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR


def cmd_project_list(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """List all active projects as JSON."""
    del args
    del tool_registry

    rows = project_registry.list_active()
    manager = ProjectManager(str(base_path), registry=project_registry)
    projects = []

    for row in rows:
        config = manager.get_project_info(row.name)
        if config is None:
            continue

        projects.append(
            {
                "id": row.id,
                "name": row.name,
                "code": config.abbreviation,
                "created_at": config.created,
            }
        )

    print(json.dumps(projects, indent=2))
    return SUCCESS
