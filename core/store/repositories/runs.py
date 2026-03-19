"""RunRepository — manages run, run_tools, and run_repos tables."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.store.connection import ConnectionFactory


class RunRepository:
    """Manages run lifecycle records."""

    def __init__(self, factory: ConnectionFactory) -> None:
        self._factory = factory

    def create_run(self, args: dict) -> int:
        """Insert a new run record. Returns the run_id (int)."""
        from datetime import UTC, datetime

        created_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs (args, created_at) VALUES (?, ?)",
                (json.dumps(args), created_at),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def add_run_tools(self, run_id: int, tools: list[dict]) -> None:
        """Insert one row per tool for a run."""
        with self._factory.connect() as conn:
            conn.executemany(
                "INSERT INTO run_tools (run_id, tool, findings_count) VALUES (?, ?, ?)",
                [
                    (run_id, t.get("tool", ""), t.get("findings_count", 0))
                    for t in tools
                ],
            )

    def add_run_repos(self, run_id: int, repos: list[str]) -> None:
        """Insert one row per repo for a run."""
        with self._factory.connect() as conn:
            conn.executemany(
                "INSERT INTO run_repos (run_id, repo) VALUES (?, ?)",
                [(run_id, repo) for repo in repos],
            )
