"""Shared fixtures for web API tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest_asyncio

from infrastructure.events.bus import EventBus
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from web.server import create_app

TEST_PORT = 12345
HANDSHAKE = "test-handshake-abc123xyz"

_BASE_FINDING: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "url": "https://original.com/path",
    "file_path": "src/app.py",
    "rule_id": "python.flask.sqli",
    "description": "SQL injection risk",
    "segment": "sast",
    "repo": "test-repo",
    "type_secret": True,
    "type_vulnerability": False,
    "profile": "test_project",
    "remediation": "old",
    "author": "jdoe",
    "commit": "abc123",
}


async def _authenticate(client: httpx.AsyncClient) -> dict[str, str]:
    """Exchange handshake for session cookies. Returns mutating-request headers."""
    resp = await client.post(
        "/api/auth/exchange",
        json={"token": HANDSHAKE},
        headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
    )
    assert resp.status_code == 200, f"exchange failed: {resp.text}"
    csrf_token = resp.json()["csrf_token"]
    # httpx stores Secure cookies in the jar but won't send them over plain
    # HTTP. Delete the auto-stored domain-specific entry, then inject a
    # domain-less copy that bypasses the Secure-flag enforcement.
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": f"http://127.0.0.1:{TEST_PORT}",
    }


@pytest_asyncio.fixture()
async def app_client(tmp_path: Path):
    """Yield (client, finding_id, rag_mock, factory, mut_headers, project_id)."""
    # DB must live at the canonical path the registry resolves to.
    db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, [_BASE_FINDING])

    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    finding_id: int = row["id"]

    rag_mock = MagicMock()
    rag_mock.get_documents = MagicMock(
        return_value={"ids": ["doc-1"], "metadatas": [{}]}
    )

    app = create_app(str(tmp_path), HANDSHAKE, port=TEST_PORT)
    # Seed the per-project RAG cache directly so chroma sync uses the mock.
    app.state.rag_engine_cache = {"testproject": rag_mock}

    _bus = EventBus()
    await _bus.register_job("finding", "finding")
    await _bus.register_job("scan", "scan")
    await _bus.register_job("triage", "triage")
    await _bus.register_job("report", "report")
    await _bus.register_job("report_draft", "report_draft")
    app.state.event_bus = _bus

    # Seed the registry so project-scoped endpoints can resolve "testproject".
    project_id = app.state.project_registry.register("testproject", str(tmp_path))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{TEST_PORT}",
    ) as client:
        mut_headers = await _authenticate(client)
        yield client, finding_id, rag_mock, factory, mut_headers, project_id
