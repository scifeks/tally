"""Tests for PATCH /api/findings/batch endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.unit.web.conftest import AUTH, TOKEN
from web.server import create_app

pytestmark = pytest.mark.integration

_FINDING_A: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "file_path": "src/a.py",
    "rule_id": "rule-a",
    "description": "finding a",
    "segment": "sast",
    "repo": "test-repo",
}
_FINDING_B: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "medium",
    "file_path": "src/b.py",
    "rule_id": "rule-b",
    "description": "finding b",
    "segment": "sast",
    "repo": "test-repo",
}


@pytest_asyncio.fixture()
async def batch_client(tmp_path: Path):
    """Yield (client, [id_a, id_b], factory) for batch endpoint tests."""
    db_path = tmp_path / "findings.db"
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, [_FINDING_A, _FINDING_B])

    with factory.connect() as conn:
        ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
        ]

    rag_mock = MagicMock()
    app = create_app(str(tmp_path), "testproject", token=TOKEN)
    app.state.connection_factory = factory
    app.state.rag_engine = rag_mock

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, ids, factory


class TestBatchPatchFindings:
    async def test_batch_approve_updates_all_rows(self, batch_client) -> None:
        client, ids, factory = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json() == {"updated": 2}
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT should_report FROM findings ORDER BY id"
            ).fetchall()
        assert all(r["should_report"] == 1 for r in rows)

    async def test_batch_sets_triaged_by_analyst_web(self, batch_client) -> None:
        client, ids, factory = batch_client
        await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=AUTH,
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings ORDER BY id"
            ).fetchall()
        for row in rows:
            assert row["triaged_by"] == "analyst_web"
            assert row["triaged_at"] is not None

    async def test_empty_ids_returns_422(self, batch_client) -> None:
        client, _, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": [], "should_report": True},
            headers=AUTH,
        )
        assert response.status_code == 422

    async def test_no_fields_returns_422(self, batch_client) -> None:
        client, ids, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": ids},
            headers=AUTH,
        )
        assert response.status_code == 422

    async def test_missing_auth_returns_401(self, batch_client) -> None:
        client, ids, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
        )
        assert response.status_code == 401

    async def test_partial_ids_returns_correct_count(self, batch_client) -> None:
        client, ids, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": [ids[0]], "should_report": True},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 1
