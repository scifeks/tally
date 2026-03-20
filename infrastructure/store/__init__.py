"""SQLite structured findings store."""

from __future__ import annotations

from pathlib import Path

from .connection import ConnectionFactory
from .repositories.audit import AuditRepository
from .repositories.findings import FindingRepository
from .repositories.runs import RunRepository
from .repositories.triage import TriageBatchRepository


def make_store(
    base_path: str | Path, project_name: str
) -> tuple[RunRepository, FindingRepository, TriageBatchRepository, AuditRepository]:
    """Create a ConnectionFactory and return all four repositories.

    The database is located at::

        <base_path>/projects/<project_name>/sqlite/findings.db

    The schema is initialised (idempotently) before the repositories are
    returned.
    """
    db_path = Path(base_path) / "projects" / project_name / "sqlite" / "findings.db"
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    return (
        RunRepository(factory),
        FindingRepository(factory),
        TriageBatchRepository(factory),
        AuditRepository(factory),
    )


__all__ = [
    "ConnectionFactory",
    "RunRepository",
    "FindingRepository",
    "TriageBatchRepository",
    "AuditRepository",
    "make_store",
]
