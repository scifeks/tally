"""Finding command handlers for the Tally CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.cli.exit_codes import (
    GENERAL_ERROR,
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError, resolve_project
from application.mcp.finding_payload import FindingPayloadError
from application.mcp.ingest_service import UnknownRepositoryError
from core.project_paths import ProjectPaths
from factories.persistence import create_ingest_service

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def _read_payload(source: str) -> dict[str, Any]:
    """Raises ValueError when the payload is unreadable or not a JSON object."""
    try:
        text = (
            sys.stdin.read()
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
        payload = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read finding payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Finding payload must be a JSON object")
    return payload


def cmd_finding_add(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Record one reviewed finding against a repository."""
    del tool_registry, base_path

    if not args.repo or not args.finding_file:
        print("Error: --repo and --finding-file are required", file=sys.stderr)
        return INVALID_ARGS

    try:
        _, row = resolve_project(project_registry, args.project)
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    try:
        payload = _read_payload(args.finding_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return INVALID_ARGS

    try:
        service = create_ingest_service(ProjectPaths.from_registry_row(row).findings_db)
        finding_id = service.record_manual_finding(
            payload, repo_name=args.repo, status=args.status
        )
    except (FindingPayloadError, UnknownRepositoryError) as exc:
        print(f"Invalid finding: {exc}", file=sys.stderr)
        return INVALID_ARGS
    except Exception as exc:
        print(f"Error recording finding: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    print(json.dumps({"finding_id": finding_id}, indent=2))
    return SUCCESS
