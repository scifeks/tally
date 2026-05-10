"""Purge command handler for the Tally CLI."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from application.chat.sealing import purge_chat_for_project
from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError, resolve_project
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from core.project_paths import ProjectPaths
from factories.persistence import (
    create_chat_session_service,
    create_findings_service,
    create_url_list_service,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_purge(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Delete findings from the knowledge base and optionally tool outputs."""
    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    tools: list[str] | None = None
    if args.tool:
        tools = [t.strip() for t in args.tool.split(",") if t.strip()]
        known = set(tool_registry.list_tool_names())
        invalid = [t for t in tools if t not in known]
        if invalid:
            print(
                f"Unknown tool(s): {', '.join(invalid)}\n"
                f"Configured tools: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return INVALID_ARGS

    keep_reports: bool = args.keep_reports

    kb_cache: dict = {}
    kb = get_or_build_knowledge_base(kb_cache, project_name, str(base_path))
    if kb is None:
        print("RAG engine unavailable", file=sys.stderr)
        return GENERAL_ERROR

    total_deleted = 0
    if tools is not None:
        for t in tools:
            total_deleted += kb.delete_findings(tool=t)
    else:
        total_deleted = kb.delete_findings(tool=None)

    paths = ProjectPaths.from_canonical(str(base_path), project_name)
    tool_outputs_dir = paths.tool_outputs_dir
    if tool_outputs_dir.exists():
        if tools is not None:
            dirs_to_clear = [tool_outputs_dir / t for t in tools]
        else:
            dirs_to_clear = [d for d in tool_outputs_dir.iterdir() if d.is_dir()]
        for tool_dir in dirs_to_clear:
            if not tool_dir.exists():
                continue
            for item in tool_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    if tools is None:
        try:
            svc = create_chat_session_service(project_registry, project_id)
            purge_chat_for_project(project_id, session_repo=svc.session_repo)
        except Exception:
            pass

    try:
        findings = create_findings_service(project_registry, project_id)
        urls = create_url_list_service(project_registry, project_id)
        if tools is None:
            urls.purge_all_url_findings()
            findings.purge_all_findings_data()
        else:
            findings.delete_findings_for_tools(tools)
            url_tools = [t for t in tools if t in {"katana", "noir"}]
            if url_tools:
                urls.delete_url_findings_for_tools(url_tools)
    except Exception as exc:
        print(f"SQLite purge warning: {exc}", file=sys.stderr)

    if tools is None and not keep_reports:
        reports_dir = paths.reports_dir
        if reports_dir.exists():
            for item in reports_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

    print(f"Deleted {total_deleted} document(s).")
    return SUCCESS
