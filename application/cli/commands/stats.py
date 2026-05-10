"""Stats command handler for the Tally CLI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.cli.exit_codes import GENERAL_ERROR, PROJECT_NOT_FOUND, SUCCESS
from application.cli.project import ProjectResolutionError, resolve_project
from application.rag.knowledge_base_cache import get_or_build_knowledge_base

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_stats(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Display knowledge base statistics for the active project."""
    del tool_registry
    try:
        _, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    kb_cache: dict = {}
    kb = get_or_build_knowledge_base(kb_cache, project_name, str(base_path))
    if kb is None:
        print("RAG engine unavailable", file=sys.stderr)
        return GENERAL_ERROR

    stats = kb.compute_stats()
    total = stats.total_documents

    if total == 0:
        print("No data ingested yet.")
        return SUCCESS

    print(f"Total Documents: {total}")
    for tool, count in sorted(stats.by_tool.items()):
        print(f"  {tool}: {count}")

    if stats.by_severity:
        print("Severity:")
        for severity, count in sorted(stats.by_severity.items()):
            print(f"  {severity}: {count}")

    if stats.last_updated:
        print(f"Last Updated: {stats.last_updated[:19].replace('T', ' ')}")

    return SUCCESS
