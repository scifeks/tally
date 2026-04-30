"""Application service for validating and applying finding updates."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from domain.tools.constants import CONFIDENCE_LEVELS, FINDING_TYPES, SEVERITY_LEVELS

# todo: This clase
if TYPE_CHECKING:
    from core.config.manager import ConfigManager
    from infrastructure.store.repositories.audit import AuditRepository
    from infrastructure.store.repositories.findings import FindingRepository


def reconstruct_abs_path(
    file: str | None, repo_name: str | None, repos: list[dict]
) -> str | None:
    """Reconstruct absolute path from relative file + repo name.

    Returns None if the resolved path would escape the repo root.
    """
    if not file or not repo_name:
        return None
    for r in repos:
        if r["name"] == repo_name:
            repo_root = r["path"].rstrip("/")
            candidate = os.path.normpath(repo_root + file)
            if not candidate.startswith(repo_root + os.sep):
                return None  # Path traversal attempt blocked
            return candidate
    return None


def resolve_repo_path(repo_name: str | None, repos: list[dict]) -> str | None:
    """Return the base directory path for repo_name, or None."""
    if not repo_name:
        return None
    for r in repos:
        if r["name"] == repo_name:
            return r["path"]
    return None


class FindingUpdateService:
    """Validates and applies enrichment updates to finding rows."""

    def __init__(
        self,
        finding_repo: FindingRepository,
        audit_repo: AuditRepository,
        config_manager: ConfigManager | None = None,
    ) -> None:
        self._finding_repo = finding_repo
        self._audit_repo = audit_repo
        self._config_manager = config_manager

    def resolve_finding_paths(
        self,
        file: str | None,
        repo_name: str | None,
        project_name: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve absolute and repo-relative paths for a finding.

        Returns (abs_path, repo_path), or (None, None) if resolution fails.
        """
        try:
            if project_name is None or self._config_manager is None:
                return (None, None)
            from core.project_paths import ProjectPaths
            from infrastructure.store.connection import ConnectionFactory
            from infrastructure.store.repositories.repositories import (
                RepositoryRepository,
            )

            paths = ProjectPaths.from_canonical(
                self._config_manager.base_path, project_name
            )
            if not paths.findings_db.exists():
                return (None, None)
            factory = ConnectionFactory(paths.findings_db)
            factory.init_schema()
            active = RepositoryRepository(factory).list_active()
            repos = [r.model_dump() for r in active]
            return (
                reconstruct_abs_path(file, repo_name, repos),
                resolve_repo_path(repo_name, repos),
            )
        except Exception:
            return (None, None)

    async def update(
        self,
        finding_id: int,
        confidence: str | None,
        finding_type: str | None,
        severity: str | None,
        reasoning: str | None,
        remediation: str | None,
        attack_vector: str | None,
        call_stack: str | None,
        strategy: str,
    ) -> bool:
        """Validate fields, apply update, write audit row. Returns True on success."""
        start = datetime.now(UTC)
        call_args: dict = {
            "finding_id": finding_id,
            "confidence": confidence,
            "finding_type": finding_type,
            "severity": severity,
            "reasoning": reasoning,
            "remediation": remediation,
            "attack_vector": attack_vector,
            "call_stack": call_stack,
            "strategy": strategy,
        }

        def _fail(err: str) -> None:
            duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
            self._audit_repo.log_event(
                "update_finding", call_args, False, err, duration_ms
            )

        # Validate required fields not None
        if confidence is None:
            err = "Missing required field: confidence"
            _fail(err)
            raise ValueError(err)
        if finding_type is None:
            err = "Missing required field: finding_type"
            _fail(err)
            raise ValueError(err)
        if severity is None:
            err = "Missing required field: severity"
            _fail(err)
            raise ValueError(err)
        if reasoning is None:
            err = "Missing required field: reasoning"
            _fail(err)
            raise ValueError(err)
        if remediation is None:
            err = "Missing required field: remediation"
            _fail(err)
            raise ValueError(err)

        # Validate enum values
        if confidence not in CONFIDENCE_LEVELS:
            err = (
                f"Invalid confidence: '{confidence}'."
                f" Must be one of: {CONFIDENCE_LEVELS}"
            )
            _fail(err)
            raise ValueError(err)
        if finding_type not in FINDING_TYPES:
            err = (
                f"Invalid finding_type: '{finding_type}'."
                f" Must be one of: {FINDING_TYPES}"
            )
            _fail(err)
            raise ValueError(err)
        if severity not in SEVERITY_LEVELS:
            err = f"Invalid severity: '{severity}'. Must be one of: {SEVERITY_LEVELS}"
            _fail(err)
            raise ValueError(err)

        try:
            result = await asyncio.to_thread(
                self._finding_repo.update_finding,
                finding_id,
                confidence,
                finding_type,
                severity,
                reasoning,
                remediation,
                attack_vector,
                call_stack,
                strategy,
                source="auto_triage",
            )
        except Exception as exc:
            duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
            self._audit_repo.log_event(
                "update_finding", call_args, False, str(exc), duration_ms
            )
            raise

        duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        self._audit_repo.log_event("update_finding", call_args, True, None, duration_ms)
        return result
