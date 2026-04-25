"""Tests for PATCH /api/v1/projects/{project_id}/findings/batch endpoint."""

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
from web.server import create_app

pytestmark = pytest.mark.integration

TEST_PORT = 12345
HANDSHAKE = "test-handshake-batch-abc123"

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
    """Yield (client, [id_a, id_b], factory, mut_headers, project_id)."""
    db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, [_FINDING_A, _FINDING_B])

    with factory.connect() as conn:
        ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
        ]

    rag_mock = MagicMock()
    app = create_app(str(tmp_path), "testproject", HANDSHAKE, port=TEST_PORT)
    app.state.connection_factory = factory
    app.state.rag_engine = rag_mock

    project_id = app.state.project_registry.register("testproject", str(tmp_path))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{TEST_PORT}",
    ) as client:
        resp = await client.post(
            "/api/auth/exchange",
            json={"token": HANDSHAKE},
            headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 200, f"exchange failed: {resp.text}"
        csrf_token = resp.json()["csrf_token"]
        for name, value in resp.cookies.items():
            client.cookies.delete(name, domain="127.0.0.1")
            client.cookies.set(name, value)
        mut_headers = {
            "X-CSRF-Token": csrf_token,
            "Origin": f"http://127.0.0.1:{TEST_PORT}",
        }
        yield client, ids, factory, mut_headers, project_id


class TestBatchPatchFindings:
    async def test_batch_approve_updates_all_rows(self, batch_client) -> None:
        client, ids, factory, mut_headers, project_id = batch_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["updated"]) == 2
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT should_report FROM findings ORDER BY id"
            ).fetchall()
        assert all(r["should_report"] == 1 for r in rows)

    async def test_batch_sets_triaged_by_analyst_web(self, batch_client) -> None:
        client, ids, factory, mut_headers, project_id = batch_client
        await client.patch(
            f"/api/v1/projects/{project_id}/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=mut_headers,
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings ORDER BY id"
            ).fetchall()
        for row in rows:
            assert row["triaged_by"] == "analyst_web"
            assert row["triaged_at"] is not None

    async def test_empty_ids_returns_422(self, batch_client) -> None:
        client, _, _, mut_headers, project_id = batch_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/batch",
            json={"ids": [], "should_report": True},
            headers=mut_headers,
        )
        assert response.status_code == 422

    async def test_no_fields_returns_422(self, batch_client) -> None:
        client, ids, _, mut_headers, project_id = batch_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/batch",
            json={"ids": ids},
            headers=mut_headers,
        )
        assert response.status_code == 422

    async def test_partial_ids_returns_correct_count(self, batch_client) -> None:
        client, ids, _, mut_headers, project_id = batch_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/batch",
            json={"ids": [ids[0]], "should_report": True},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["updated"]) == 1
