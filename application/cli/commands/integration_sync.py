"""Integration sync command handler for the Tally CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.exit_codes import (
    GENERAL_ERROR,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import (
    ProjectResolutionError,
    resolve_project,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import (
        ProjectRegistryService,
    )
    from application.tools.registry import ToolRegistry


def cmd_integration_sync(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    del tool_registry
    try:
        project_id, _ = resolve_project(project_registry, args.project)
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    from factories.export import (
        ExportNotConfigured,
        create_export_service,
    )

    try:
        service = create_export_service(project_registry, project_id, base_path)
    except ExportNotConfigured as exc:
        print(str(exc), file=sys.stderr)
        return GENERAL_ERROR

    run_id: int | None = getattr(args, "run_id", None)
    result = service.export(run_id=run_id)

    if not result.success:
        for error in result.errors:
            print(error, file=sys.stderr)
        return GENERAL_ERROR

    print(
        f"Exported {result.findings_exported} findings"
        f" to DefectDojo"
        + (
            f" ({result.findings_failed} failed to map)"
            if result.findings_failed
            else ""
        )
    )
    return SUCCESS
