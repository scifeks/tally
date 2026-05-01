"""Integration tests for /api/v1/tools/catalog and .../tools/overrides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from application.tools.registry import tool_registry
from infrastructure.store.connection import ConnectionFactory
from tests.integration.web.conftest import (
    HANDSHAKE,
    TEST_PORT,
    _authenticate,
)
from web.server import create_app

pytestmark = pytest.mark.integration

_PROJECT_CONFIG: dict[str, Any] = {
    "project_name": "Test Project",
    "created": "2024-01-01T00:00:00",
    "abbreviation": "TP",
    "company_name": "Acme Corp",
    "department_name": "Security",
    "repositories": [
        {
            "name": "test-repo",
            "type": ["api"],
            "path": "",
            "docker_path": "/app",
            "container_name": "test_container",
            "languages": ["python"],
            "base_urls": ["http://localhost"],
            "auth": {
                "login_url": "http://localhost/login",
                "username": "admin",
                "password": "secret",
            },
        }
    ],
}


class _FakeTool:
    """Minimal duck-typed stand-in for ToolWrapper used in catalog tests."""

    def __init__(
        self,
        name: str,
        category: str,
        description: str,
        installed: bool = True,
    ) -> None:
        self.name = name
        self.category = category
        self.description = description
        self._installed = installed

    def check_available(self) -> bool:
        return self._installed


@pytest_asyncio.fixture()
async def tools_v1_client(tmp_path: Path):
    """Yield (client, mut_headers, tmp_path) with a real project on disk."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text("{}")

    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    (proj_dir / "config" / "project.json").write_text(json.dumps(_PROJECT_CONFIG))

    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    kb_mock = MagicMock()
    kb_mock.get.return_value = []

    app = create_app(str(tmp_path), HANDSHAKE, port=TEST_PORT)
    app.state.knowledge_base_cache = {"testproject": kb_mock}

    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = int(row["id"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{TEST_PORT}",
    ) as client:
        mut_headers = await _authenticate(client)
        yield client, mut_headers, tmp_path, project_id


def _make_unauthed_app(tmp_path: Path) -> Any:
    """Return a minimal FastAPI app for unauthenticated auth tests."""

    db_path = tmp_path / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    app = create_app(str(tmp_path), "tok", port=TEST_PORT)
    return app


class TestToolsCatalog:
    async def test_catalog_returns_items(self, app_client) -> None:
        client, *_ = app_client
        tool_registry.clear()
        tool_registry.register(_FakeTool("bandit", "sast", "Python security linter"))
        tool_registry.register(_FakeTool("gitleaks", "secrets", "Secret scanner"))
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_catalog_item_fields(self, app_client) -> None:
        client, *_ = app_client
        tool_registry.clear()
        tool_registry.register(_FakeTool("bandit", "sast", "Python security linter"))
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["id"] == "bandit"
        assert item["name"] == "Bandit"
        assert item["domain"] == "sast"
        assert isinstance(item["supports_local"], bool)
        assert isinstance(item["supports_docker"], bool)
        assert item["description"] == "Python security linter"

    async def test_catalog_empty_when_no_tools(self, app_client) -> None:
        client, *_ = app_client
        tool_registry.clear()
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_catalog_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"http://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code in (401, 403)


class TestInstalledTools:
    async def test_returns_only_available_tools(self, app_client) -> None:
        from infrastructure.system.installed_tools_probe import InstalledToolsProbe

        client, *_ = app_client
        tool_registry.clear()
        tool_registry.register(
            _FakeTool("bandit", "sast", "Python linter", installed=True)
        )
        tool_registry.register(
            _FakeTool("nuclei", "dast", "Web scanner", installed=False)
        )
        tool_registry.register(
            _FakeTool("gitleaks", "secrets", "Secret scanner", installed=True)
        )
        # Re-probe after the registry was rewritten by the fixture.
        client._transport.app.state.installed_tools = (  # type: ignore[attr-defined]
            InstalledToolsProbe()
        )

        resp = await client.get("/api/v1/tools/installed")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"installed": ["bandit", "gitleaks"]}

    async def test_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"http://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/tools/installed")
        assert resp.status_code in (401, 403)


class TestToolOverrides:
    async def test_overrides_empty_when_no_file(self, tools_v1_client) -> None:
        client, _, _, project_id = tools_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/tools/overrides")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_overrides_returns_project_entries(self, tools_v1_client) -> None:
        client, _, tmp_path, project_id = tools_v1_client
        overrides = {
            "bandit": {
                "type": "repo",
                "location": "local",
                "path": "/usr/local/bin/bandit",
            },
            "nuclei": {
                "type": "api",
                "location": "docker",
                "container": {
                    "name": "tally-nuclei",
                    "tool_path": "/usr/bin/nuclei",
                },
            },
        }
        commands_path = (
            tmp_path / "projects" / "testproject" / "config" / "commands.json"
        )
        commands_path.write_text(json.dumps(overrides))

        resp = await client.get(f"/api/v1/projects/{project_id}/tools/overrides")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        by_id = {item["tool_id"]: item for item in data["items"]}

        bandit = by_id["bandit"]
        assert bandit["location"] == "local"
        assert bandit["path"] == "/usr/local/bin/bandit"
        assert bandit["container"] is None

        nuclei = by_id["nuclei"]
        assert nuclei["location"] == "docker"
        assert nuclei["container"]["name"] == "tally-nuclei"
        assert nuclei["container"]["tool_path"] == "/usr/bin/nuclei"

    async def test_overrides_strips_empty_path(self, tools_v1_client) -> None:
        client, _, tmp_path, project_id = tools_v1_client
        overrides = {
            "nuclei": {
                "type": "api",
                "location": "docker",
                "container": {
                    "name": "tally-nuclei",
                    "tool_path": "/usr/bin/nuclei",
                },
            }
        }
        commands_path = (
            tmp_path / "projects" / "testproject" / "config" / "commands.json"
        )
        commands_path.write_text(json.dumps(overrides))

        resp = await client.get(f"/api/v1/projects/{project_id}/tools/overrides")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["path"] is None

    async def test_overrides_404_unknown_project(self, tools_v1_client) -> None:
        client, _, _, _ = tools_v1_client
        resp = await client.get("/api/v1/projects/9999/tools/overrides")
        assert resp.status_code == 404
        assert "error" in resp.json()

    async def test_overrides_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"http://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/projects/9999/tools/overrides")
        assert resp.status_code in (401, 403)


class TestToolOverridesWriteCRUD:
    """POST/PUT/DELETE coverage for ``/api/v1/projects/:id/tools/overrides``.

    Each successful write must call ``discover_tools`` so the in-memory
    registry reflects the change immediately. We verify that side-effect
    by patching the call site in ``web.api.tools``.
    """

    @staticmethod
    def _read_overrides(tmp_path: Path) -> dict:
        commands_path = (
            tmp_path / "projects" / "testproject" / "config" / "commands.json"
        )
        if not commands_path.exists():
            return {}
        return json.loads(commands_path.read_text())

    async def test_post_creates_override_and_refreshes_registry(
        self, tools_v1_client, monkeypatch
    ) -> None:
        client, headers, tmp_path, project_id = tools_v1_client
        called: list[tuple[str, str | None]] = []

        def _spy(base_path: str, project_name: str | None = None) -> None:
            called.append((base_path, project_name))

        monkeypatch.setattr("web.api.tools.discover_tools", _spy)

        body = {
            "tool_id": "bandit",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/bandit",
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        item = resp.json()
        assert item["tool_id"] == "bandit"
        assert item["location"] == "local"
        assert item["path"] == "/usr/local/bin/bandit"

        # CommandEntry.model_dump() includes ``container: None`` for local
        # entries; assert on the meaningful fields rather than full equality.
        overrides = self._read_overrides(tmp_path)
        assert "bandit" in overrides
        assert overrides["bandit"]["type"] == "repo"
        assert overrides["bandit"]["location"] == "local"
        assert overrides["bandit"]["path"] == "/usr/local/bin/bandit"
        assert called and called[-1][1] == "testproject", (
            "discover_tools must run after a successful POST"
        )

    async def test_post_duplicate_returns_409(self, tools_v1_client) -> None:
        client, headers, tmp_path, project_id = tools_v1_client
        commands_path = (
            tmp_path / "projects" / "testproject" / "config" / "commands.json"
        )
        commands_path.write_text(
            json.dumps({"bandit": {"type": "repo", "location": "local"}})
        )
        body = {
            "tool_id": "bandit",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/bandit",
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_post_invalid_payload_returns_422(self, tools_v1_client) -> None:
        client, headers, _, project_id = tools_v1_client
        # Missing required tool_id.
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json={"type": "repo", "location": "local"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_post_without_csrf_returns_403(self, tools_v1_client) -> None:
        client, _, _, project_id = tools_v1_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json={
                "tool_id": "bandit",
                "type": "repo",
                "location": "local",
                "path": "/x",
            },
        )
        assert resp.status_code == 403

    async def test_put_replaces_override_and_refreshes_registry(
        self, tools_v1_client, monkeypatch
    ) -> None:
        client, headers, tmp_path, project_id = tools_v1_client
        commands_path = (
            tmp_path / "projects" / "testproject" / "config" / "commands.json"
        )
        commands_path.write_text(
            json.dumps(
                {"bandit": {"type": "repo", "location": "local", "path": "/old"}}
            )
        )
        called: list[tuple[str, str | None]] = []
        monkeypatch.setattr(
            "web.api.tools.discover_tools",
            lambda bp, project_name=None: called.append((bp, project_name)),
        )

        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/bandit",
            json={"type": "repo", "location": "local", "path": "/new"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["path"] == "/new"
        assert self._read_overrides(tmp_path)["bandit"]["path"] == "/new"
        assert called and called[-1][1] == "testproject"

    async def test_put_unknown_returns_404(self, tools_v1_client) -> None:
        client, headers, _, project_id = tools_v1_client
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/unknown",
            json={"type": "repo", "location": "local", "path": "/x"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_put_without_csrf_returns_403(self, tools_v1_client) -> None:
        client, _, _, project_id = tools_v1_client
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/bandit",
            json={"type": "repo", "location": "local", "path": "/x"},
        )
        assert resp.status_code == 403

    async def test_delete_removes_override_and_refreshes_registry(
        self, tools_v1_client, monkeypatch
    ) -> None:
        client, headers, tmp_path, project_id = tools_v1_client
        commands_path = (
            tmp_path / "projects" / "testproject" / "config" / "commands.json"
        )
        commands_path.write_text(
            json.dumps(
                {
                    "bandit": {
                        "type": "repo",
                        "location": "local",
                        "path": "/x",
                    }
                }
            )
        )
        called: list[tuple[str, str | None]] = []
        monkeypatch.setattr(
            "web.api.tools.discover_tools",
            lambda bp, project_name=None: called.append((bp, project_name)),
        )

        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/bandit",
            headers=headers,
        )
        assert resp.status_code == 204
        assert "bandit" not in self._read_overrides(tmp_path)
        assert called and called[-1][1] == "testproject"

    async def test_delete_unknown_returns_404(self, tools_v1_client) -> None:
        client, headers, _, project_id = tools_v1_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/missing",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_delete_without_csrf_returns_403(self, tools_v1_client) -> None:
        client, _, _, project_id = tools_v1_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/bandit",
        )
        assert resp.status_code == 403


class TestRuntimeDependencies:
    async def test_returns_dependencies_list(self, app_client) -> None:
        client, *_ = app_client
        resp = await client.get("/api/v1/runtime-dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert "dependencies" in data
        assert isinstance(data["dependencies"], list)

    async def test_dependency_item_fields(self, app_client) -> None:
        client, *_ = app_client
        resp = await client.get("/api/v1/runtime-dependencies")
        assert resp.status_code == 200
        deps = resp.json()["dependencies"]
        assert len(deps) >= 1
        item = deps[0]
        assert item["name"] == "claude"
        assert isinstance(item["installed"], bool)
        assert isinstance(item["required_for"], list)
        assert isinstance(item["install_hint"], str)
        assert "binary_path" in item
        assert "version" in item
        assert "error" in item

    async def test_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"http://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/runtime-dependencies")
        assert resp.status_code in (401, 403)
