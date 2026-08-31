"""Integration tests for MCP serve endpoints."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.mcp.registry import McpServerHandle, get_mcp_server_registry
from core.security.credentials import decrypt_value, get_encryption_key
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.mcp_tokens import McpTokenRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.finding_helpers import normalize_test_findings
from web.api import mcp_serve

pytestmark = pytest.mark.integration


_BATCHABLE_FINDING: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "segment": "sast",
    "severity": "high",
    "confidence": "potential",
    "file": "src/app.py",
    "rule_id": "python.sqli",
    "description": "SQL injection",
}


@pytest.fixture(autouse=True)
def _reset_mcp_registry():
    """Reset the process-singleton MCP server registry between tests."""
    get_mcp_server_registry().reset()
    yield
    get_mcp_server_registry().reset()


def _seed_repo(factory: ConnectionFactory, name: str = "test-repo") -> int:
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, path) VALUES (?, ?)",
            (name, "/tmp/fakerepo"),
        )
        return cur.lastrowid  # type: ignore[return-value]


def _seed_batchable_run(factory: ConnectionFactory) -> None:
    """Seed a scan run with one active, batchable finding."""
    repo_id = _seed_repo(factory)
    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding = {**_BATCHABLE_FINDING, "repo_id": repo_id}
    finding_repo.insert_findings(run_id, normalize_test_findings([finding]))


def _fake_start_mcp_server_managed(**kwargs: Any) -> McpServerHandle:
    """Register a handle without binding a real network port."""
    handle = McpServerHandle(
        host=kwargs["host"],
        port=kwargs["port"],
        source=kwargs["source"],
        server=MagicMock(),
        thread=threading.Thread(target=lambda: None),
    )
    get_mcp_server_registry().register(handle)
    return handle


# POST /{project_id}/mcp/triage/start


@pytest.mark.asyncio
async def test_start_404_when_no_scan_runs(app_client) -> None:
    client, *_, mut_headers, _project_id = app_client
    create_resp = await client.post(
        "/api/v1/projects",
        json={"name": "mcp-empty-project"},
        headers=mut_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    empty_project_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{empty_project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_start_creates_batches_and_starts_server(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_batchable_run(factory)

    fake_start = MagicMock(side_effect=_fake_start_mcp_server_managed)
    monkeypatch.setattr(mcp_serve, "start_mcp_server_managed", fake_start)

    resp = await client.post(
        f"/api/v1/projects/{project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["batchCount"] == 1
    assert body["totalFindings"] == 1
    assert body["host"]
    assert isinstance(body["port"], int)
    assert body["token"]

    fake_start.assert_called_once()
    assert get_mcp_server_registry().is_active()


@pytest.mark.asyncio
async def test_start_auto_creates_token_that_decrypts_to_response_value(
    app_client, monkeypatch, tmp_path: Path
) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_batchable_run(factory)
    monkeypatch.setattr(
        mcp_serve, "start_mcp_server_managed", _fake_start_mcp_server_managed
    )

    resp = await client.post(
        f"/api/v1/projects/{project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert resp.status_code == 202, resp.text
    token_value = resp.json()["token"]

    token_repo = McpTokenRepository(tmp_path / "tally.db")
    encrypted_tokens = token_repo.get_all_encrypted()
    assert len(encrypted_tokens) == 1

    encryption_key = get_encryption_key(tmp_path / "mcp_credentials.key")
    assert decrypt_value(encrypted_tokens[0], encryption_key) == token_value


@pytest.mark.asyncio
async def test_start_second_call_reuses_server_and_existing_token(
    app_client, monkeypatch
) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_batchable_run(factory)
    fake_start = MagicMock(side_effect=_fake_start_mcp_server_managed)
    monkeypatch.setattr(mcp_serve, "start_mcp_server_managed", fake_start)

    first = await client.post(
        f"/api/v1/projects/{project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert first.status_code == 202, first.text

    second = await client.post(
        f"/api/v1/projects/{project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert second.status_code == 202, second.text
    assert second.json()["token"] == "<use existing token>"
    fake_start.assert_called_once()


# GET /mcp/serve/status


@pytest.mark.asyncio
async def test_status_inactive_by_default(app_client) -> None:
    client, *_ = app_client
    resp = await client.get("/api/v1/mcp/serve/status")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "active": False,
        "host": None,
        "port": None,
        "source": None,
    }


@pytest.mark.asyncio
async def test_status_reflects_active_server(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_batchable_run(factory)
    monkeypatch.setattr(
        mcp_serve, "start_mcp_server_managed", _fake_start_mcp_server_managed
    )
    start_resp = await client.post(
        f"/api/v1/projects/{project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert start_resp.status_code == 202, start_resp.text

    resp = await client.get("/api/v1/mcp/serve/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active"] is True
    assert body["source"] == "web"
    assert body["port"] == start_resp.json()["port"]


# POST /mcp/serve/stop


@pytest.mark.asyncio
async def test_stop_404_when_no_active_server(app_client) -> None:
    client, *_, mut_headers, _project_id = app_client
    resp = await client.post("/api/v1/mcp/serve/stop", headers=mut_headers)
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_stop_returns_status_stopped_when_active(app_client, monkeypatch) -> None:
    client, _fid, _rag, factory, mut_headers, project_id = app_client
    _seed_batchable_run(factory)
    monkeypatch.setattr(
        mcp_serve, "start_mcp_server_managed", _fake_start_mcp_server_managed
    )
    start_resp = await client.post(
        f"/api/v1/projects/{project_id}/mcp/triage/start",
        headers=mut_headers,
    )
    assert start_resp.status_code == 202, start_resp.text

    resp = await client.post("/api/v1/mcp/serve/stop", headers=mut_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "stopped"}
