"""Shared fixtures and helpers for tests/integration/mcp/."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.audit import AuditRepository  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from infrastructure.store.repositories.triage import TriageBatchRepository  # noqa: E402
from tally_mcp.context import FindingsContext  # noqa: E402
from tally_mcp.tools import findings  # noqa: E402

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "medium",
    "file_path": "src/app.py",
    "rule_id": "python.flask.sqli",
    "description": "SQL injection risk",
}

_VALID_UPDATE = {
    "confidence": "probable",
    "finding_type": "vulnerability",
    "severity": "high",
    "reasoning": "Code review confirms taint flow reaches sink.",
    "remediation": "Parameterise the query.",
    "attack_vector": "network",
    "call_stack": None,
    "strategy": "manual",
}


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    overrides: dict | None = None,
) -> None:
    finding = {**_BASE_FINDING, **(overrides or {})}
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, [finding])


def _first_id(factory: ConnectionFactory) -> int:
    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    assert row is not None
    return row["id"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(
        tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    )
    f.init_schema()
    return f


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def finding_repo(factory: ConnectionFactory) -> FindingRepository:
    return FindingRepository(factory)


@pytest.fixture()
def audit_repo(factory: ConnectionFactory) -> AuditRepository:
    return AuditRepository(factory)


@pytest.fixture()
def triage_repo(factory: ConnectionFactory) -> TriageBatchRepository:
    return TriageBatchRepository(factory)


@pytest.fixture()
def store(
    factory: ConnectionFactory,
    finding_repo: FindingRepository,
    audit_repo: AuditRepository,
    triage_repo: TriageBatchRepository,
) -> ConnectionFactory:
    """Return factory with all repos injected into findings module."""
    findings.init(
        FindingsContext(
            finding_repo=finding_repo,
            audit_repo=audit_repo,
            triage_repo=triage_repo,
            project_name="",
        )
    )
    return factory
