"""Project-related MCP tools."""

import asyncio
import json
from pathlib import Path

_app_root: Path = Path(__file__).parent.parent.parent


async def get_project_config(project: str) -> dict:
    """Retrieve configuration metadata for a project.

    Args:
        project: The project name whose configuration should be returned.

    Returns:
        A dict containing project configuration details such as repositories,
        enabled tools, and project-level settings.

    Raises:
        FileNotFoundError: If no project.json exists for the given project.
    """
    path = _app_root / "projects" / project / "config" / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"Project config not found: {path}")
    return await asyncio.to_thread(lambda: json.loads(path.read_text()))
