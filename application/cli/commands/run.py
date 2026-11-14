"""Run command handler for the Tally CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.adapters import CliProgressReporter, CliPromptAdapter
from application.cli.exit_codes import GENERAL_ERROR, PROJECT_NOT_FOUND, SUCCESS
from application.cli.project import ProjectResolutionError, resolve_project
from application.tools.executor import DEFAULT_TIMEOUT, ToolExecutor
from core.project_paths import ProjectPaths
from factories.persistence import create_overrides_repo
from factories.scanning import create_subprocess_runner
from infrastructure.tools.cli_runner import CliToolRunner

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_run(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Invoke a single tool and return an exit code."""
    try:
        _, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    tool_name = args.tool.lower()
    timeout = args.timeout
    remaining = args.args or []

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
        return _cmd_run_inner(
            tool_name,
            timeout,
            remaining,
            tool_registry,
            project_name,
            base_path,
        )
    finally:
        discover_tools(tool_registry, str(base_path))


def _cmd_run_inner(
    tool_name: str,
    timeout: int | None,
    remaining: list[str],
    tool_registry: ToolRegistry,
    project_name: str,
    base_path: Path,
) -> int:
    """Look up the tool, check availability, execute."""
    tool = tool_registry.get_tool(tool_name)
    if tool is None:
        print(f"Tool not found: {tool_name}", file=sys.stderr)
        return GENERAL_ERROR

    if not tool.check_available():
        print(f"Tool not installed: {tool_name}", file=sys.stderr)
        return GENERAL_ERROR

    try:
        executor = ToolExecutor(
            project_name=project_name,
            base_path=Path(base_path),
            prompt=CliPromptAdapter(),
            cli_tool_runner=CliToolRunner(create_subprocess_runner()),
            reporter=CliProgressReporter(),
        )
        result = executor.execute(
            tool,
            timeout=timeout or DEFAULT_TIMEOUT,
            label="manual",
            args=" ".join(remaining),
            hosts=[],
        )

        if result.output_files:
            for path in result.output_files.values():
                print(f"Output saved to: {path}")

        return SUCCESS
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return GENERAL_ERROR
