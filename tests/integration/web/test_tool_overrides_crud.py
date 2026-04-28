"""Integration tests for tool override CRUD endpoints (Phase 9.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from infrastructure.store.connection import ConnectionFactory
from web.server import create_app

pytestmark = pytest.mark.integration

_TEST_PORT = 12348
_HANDSHAKE = "test-handshake-abc123xyz"

_PROJECT_CONFIG: dict[str, Any] = {
    "project_name": "Test Project",
    "created": "2024-01-01T00:00:00",
    "abbreviation": "TP",
    "company_name": "Acme Corp",
    "department_name": "Security",
    "repositories": [],
}


async def _auth(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/exchange",
        json={"token": _HANDSHAKE},
        headers={"origin": f"http://127.0.0.1:{_TEST_PORT}"},
    )
    assert resp.status_code == 200
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    csrf_token = client.cookies["tally_csrf"]
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": f"http://127.0.0.1:{_TEST_PORT}",
    }


@pytest_asyncio.fixture()
async def overrides_client(tmp_path: Path):
    """Yield (client, mut_headers, project_id, override_path)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text("{}")
    (config_dir / "commands.json").write_text("{}")

    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    (proj_dir / "config" / "project.json").write_text(json.dumps(_PROJECT_CONFIG))

    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    app = create_app(str(tmp_path), _HANDSHAKE, port=_TEST_PORT)
    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = int(row["id"])
    override_path = proj_dir / "config" / "commands.json"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{_TEST_PORT}",
    ) as client:
        mut_headers = await _auth(client)
        yield client, mut_headers, project_id, override_path


_LOCAL_BODY = {
    "tool_id": "semgrep",
    "type": "repo",
    "location": "local",
    "path": "/usr/bin/semgrep",
}


_DOCKER_BODY = {
    "tool_id": "gitleaks",
    "type": "repo",
    "location": "docker",
    "path": "",
    "container": {"name": "gitleaks-runner", "tool_path": "/app/gitleaks"},
}


class TestCreateOverride:
    async def test_post_local_tool_returns_201(self, overrides_client) -> None:
        client, headers, pid, path = overrides_client
        resp = await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["tool_id"] == "semgrep"
        assert body["location"] == "local"
        assert body["path"] == "/usr/bin/semgrep"
        # Persisted to disk.
        on_disk = json.loads(path.read_text())
        assert "semgrep" in on_disk

    async def test_post_docker_tool_returns_201(self, overrides_client) -> None:
        client, headers, pid, _ = overrides_client
        resp = await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_DOCKER_BODY,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["container"]["name"] == "gitleaks-runner"
        assert body["container"]["tool_path"] == "/app/gitleaks"

    async def test_post_duplicate_returns_409(self, overrides_client) -> None:
        client, headers, pid, _ = overrides_client
        await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        resp = await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_post_local_without_path_returns_422(self, overrides_client) -> None:
        client, headers, pid, _ = overrides_client
        bad = {"tool_id": "x", "type": "repo", "location": "local", "path": ""}
        resp = await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=bad,
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_post_without_csrf_returns_403(self, overrides_client) -> None:
        client, _, pid, _ = overrides_client
        resp = await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
        )
        assert resp.status_code == 403

    async def test_post_override_appears_in_get_list(self, overrides_client) -> None:
        """After POST, GET /tools/overrides reflects the new override."""
        client, headers, pid, _ = overrides_client
        await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        resp = await client.get(f"/api/v1/projects/{pid}/tools/overrides")
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = [item["tool_id"] for item in data["items"]]
        assert "semgrep" in tool_ids
        assert data["total"] == 1

    async def test_create_override_calls_discover_tools(
        self, overrides_client, monkeypatch
    ) -> None:
        """POST /tools/overrides calls discover_tools to refresh the registry (F2)."""
        client, headers, pid, _ = overrides_client
        calls: list = []
        monkeypatch.setattr(
            "web.api.tools.discover_tools",
            lambda *a, **kw: calls.append((a, kw)),
        )
        resp = await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        assert resp.status_code == 201
        assert calls, "discover_tools must be called after POST override"


class TestReplaceOverride:
    async def test_put_replaces_entry(self, overrides_client) -> None:
        client, headers, pid, path = overrides_client
        await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        resp = await client.put(
            f"/api/v1/projects/{pid}/tools/overrides/semgrep",
            json={
                "type": "api",
                "location": "local",
                "path": "/opt/semgrep",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["type"] == "api"
        assert body["path"] == "/opt/semgrep"
        on_disk = json.loads(path.read_text())
        assert on_disk["semgrep"]["path"] == "/opt/semgrep"

    async def test_put_unknown_returns_404(self, overrides_client) -> None:
        client, headers, pid, _ = overrides_client
        resp = await client.put(
            f"/api/v1/projects/{pid}/tools/overrides/unknown",
            json={"type": "repo", "location": "local", "path": "/x"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestDeleteOverride:
    async def test_delete_removes_entry(self, overrides_client) -> None:
        client, headers, pid, path = overrides_client
        await client.post(
            f"/api/v1/projects/{pid}/tools/overrides",
            json=_LOCAL_BODY,
            headers=headers,
        )
        resp = await client.delete(
            f"/api/v1/projects/{pid}/tools/overrides/semgrep",
            headers=headers,
        )
        assert resp.status_code == 204
        on_disk = json.loads(path.read_text())
        assert "semgrep" not in on_disk

    async def test_delete_unknown_returns_404(self, overrides_client) -> None:
        client, headers, pid, _ = overrides_client
        resp = await client.delete(
            f"/api/v1/projects/{pid}/tools/overrides/nonexistent",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_delete_unknown_project_returns_404(self, overrides_client) -> None:
        client, headers, _, _ = overrides_client
        resp = await client.delete(
            "/api/v1/projects/9999/tools/overrides/semgrep",
            headers=headers,
        )
        assert resp.status_code == 404
