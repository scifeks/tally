"""Shared fixtures for web API tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest_asyncio

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from web.server import create_app

TOKEN = "test-token-abc123"
AUTH: dict[str, str] = {"Authorization": f"Bearer {TOKEN}"}

# Finding used to seed the test database before each test.
# Keys not in _CHROMA_TO_SQLITE go to the meta JSON blob.
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
    # -- meta blob keys --
    "type_secret": True,
    "type_vulnerability": False,
    "profile": "test_project",
    "remediation": "old",
    "author": "jdoe",
    "commit": "abc123",
}


@pytest_asyncio.fixture()
async def app_client(tmp_path: Path):
    """Yield (client, finding_id, rag_mock, factory) for web API tests.

    Sets up a real SQLite database, seeds one finding, wires a mock
    RAGEngine, and returns an httpx.AsyncClient backed by the FastAPI app.
    """
    db_path = tmp_path / "findings.db"
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, [_BASE_FINDING])

    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings LIMIT 1").fetchone()
    finding_id: int = row["id"]

    rag_mock = MagicMock()
    rag_mock.get_documents = MagicMock(
        return_value={"ids": ["doc-1"], "metadatas": [{}]}
    )
    rag_mock.update_metadata = MagicMock()

    app = create_app(str(tmp_path), "testproject", token=TOKEN)
    app.state.connection_factory = factory
    app.state.rag_engine = rag_mock

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, finding_id, rag_mock, factory
