"""Project-related MCP tools."""

import asyncio
import json
from pathlib import Path

from infrastructure.store.project_registry import ProjectRegistryRepository

_app_root: Path = Path(__file__).parent.parent.parent


def _project_root(project: str) -> Path:
    """Resolve project's on-disk root via tally.db, with canonical fallback."""
    tally_db = _app_root / "tally.db"
    if tally_db.exists():
        try:
            row = ProjectRegistryRepository(tally_db).get_by_name(project)
        except Exception:
            row = None
        if row is not None and row.archived_at is None:
            return Path(row.path)
    from core.project_paths import ProjectPaths

    return ProjectPaths.from_canonical(_app_root, project).root


async def get_project_config(project: str) -> dict:
    """Retrieve configuration metadata for a project."""
    path = _project_root(project) / "config" / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")
    return await asyncio.to_thread(lambda: json.loads(path.read_text()))
