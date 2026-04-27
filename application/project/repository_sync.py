"""Lazy backfill of the per-project ``repositories`` table from project.json.

Phase 9 introduces a stable integer ``id`` per repo (carried in the per-project
SQLite ``repositories`` table) and an immutable ``uuid`` (the JSON-side
identifier persisted in ``projects/<p>/config/project.json``).

This module's ``sync_repositories_for_project`` is called at REPL/web startup
for each known project. It:

1. Reads ``project.json`` under the project config lock.
2. For every repo entry without a ``uuid``, stamps a fresh ``uuid4`` and
   writes the JSON back atomically.
3. For every (uuid, name) pair, ensures a matching active row exists in the
   per-project ``repositories`` table (insert if absent; rename if name has
   drifted in JSON since last sync).
4. Backfills ``findings.repo_id`` from the legacy ``findings.repo`` string
   column where ``repo_id IS NULL`` and a matching ``repositories`` row
   exists.

Idempotent. No-op once everything is already in sync.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from core.config._atomic import atomic_write_text, locked_config
from core.project_paths import ProjectPaths
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository

logger = logging.getLogger(__name__)


def sync_repositories_for_project(project_path: str) -> None:
    """Backfill uuid + ``repositories`` rows + ``findings.repo_id`` for one project.

    *project_path* is the absolute project root (the ``path`` column from the
    global ``projects`` registry row). Pass the registry value rather than
    ``<base>/projects/<name>`` so that projects whose physical location has
    drifted are still synced correctly.
    """
    paths = ProjectPaths(Path(project_path))
    config_path = paths.config_json
    if not config_path.exists():
        return

    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    repo_repo = RepositoryRepository(factory)

    with locked_config(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "sync_repositories_for_project: failed to load %s: %s",
                config_path,
                exc,
            )
            return

        repos = data.get("repositories")
        if not isinstance(repos, list):
            return

        json_changed = False
        rename_pairs: list[tuple[str, str]] = []
        for entry in repos:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "")
            if not isinstance(name, str) or not name:
                continue
            uuid_str = entry.get("uuid") or ""
            if not uuid_str:
                uuid_str = str(uuid4())
                entry["uuid"] = uuid_str
                json_changed = True
                rename_pairs.append((name, uuid_str))
            existing = repo_repo.get_by_uuid(uuid_str)
            if existing is None:
                repo_repo.insert(uuid=uuid_str, name=name)
            elif existing.name != name:
                repo_repo.rename(existing.id, name)

        if json_changed:
            atomic_write_text(config_path, json.dumps(data, indent=2))

    _backfill_findings_repo_id(factory)
    _migrate_endpoint_dirs(paths, rename_pairs)


def _migrate_endpoint_dirs(
    paths: ProjectPaths, rename_pairs: list[tuple[str, str]]
) -> None:
    """Rename legacy ``endpoints/<name>/`` to ``endpoints/<uuid>/``.

    Phase 9 keys repo endpoint directories by uuid (immutable across
    renames) instead of name. For projects predating Phase 9 a
    name-keyed directory may still exist; this helper performs a
    one-shot, idempotent rename whenever the freshly-stamped uuid has
    no on-disk dir but the prior name does. Per pair: if both dirs
    exist (the user already created the uuid one) we leave both alone
    rather than risk merging.
    """
    if not rename_pairs:
        return
    endpoints_dir = paths.endpoints_dir
    if not endpoints_dir.exists():
        return
    for old_name, new_uuid in rename_pairs:
        old_dir = endpoints_dir / old_name
        new_dir = endpoints_dir / new_uuid
        if old_dir.is_dir() and not new_dir.exists():
            try:
                old_dir.rename(new_dir)
            except OSError as exc:
                logger.warning(
                    "endpoint dir rename failed (%s -> %s): %s",
                    old_dir,
                    new_dir,
                    exc,
                )


def _backfill_findings_repo_id(factory: ConnectionFactory) -> None:
    """One-shot UPDATE: populate ``findings.repo_id`` from the repo name.

    Two code paths:
    - Legacy schema (``repo`` TEXT column exists): backfill from that column.
    - B1 schema (``repo`` column removed): backfill from ``meta`` JSON blob
      where the repo name is stored under key ``"repo"``.

    Idempotent; no-op when nothing needs backfilling.
    """
    with factory.connect() as conn:
        cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(findings)").fetchall()
        }
        if "repo_id" not in cols:
            return
        if "repo" in cols:
            conn.execute(
                "UPDATE findings SET repo_id = ("
                "  SELECT id FROM repositories WHERE name = findings.repo"
                ") WHERE repo_id IS NULL AND repo IS NOT NULL"
            )
        else:
            conn.execute(
                "UPDATE findings SET repo_id = ("
                "  SELECT id FROM repositories"
                "  WHERE name = json_extract(findings.meta, '$.repo')"
                ") WHERE repo_id IS NULL"
                "  AND json_extract(findings.meta, '$.repo') IS NOT NULL"
            )


def sync_repositories_for_all_projects(base_path: str) -> None:
    """Run :func:`sync_repositories_for_project` for every active project.

    Imports ``ProjectRegistryService`` lazily to avoid a circular import.
    Safe to call repeatedly (idempotent per project).
    """
    from infrastructure.store.project_registry import ProjectRegistryRepository

    registry = ProjectRegistryRepository(Path(base_path) / "tally.db")
    if not registry.db_path.exists():
        return
    registry.init_schema()
    for row in registry.list_active():
        try:
            sync_repositories_for_project(row["path"])
        except Exception as exc:
            logger.warning(
                "sync_repositories_for_all_projects: project %r failed: %s",
                row.get("name"),
                exc,
            )
