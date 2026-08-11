"""Integration tests for /api/v1/tools/catalog and .../tools/overrides."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from infrastructure.store.connection import ConnectionFactory
from tests._app_factory import build_test_app
from tests.integration.web.conftest import (
    HANDSHAKE,
    TEST_PORT,
    _authenticate,
)

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
        requires_base_urls: bool = False,
    ) -> None:
        self.name = name
        self.category = category
        self.description = description
        self._installed = installed
        self.requires_base_urls = requires_base_urls

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

    app = build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)
    app.state.knowledge_base_cache = {"testproject": kb_mock}

    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = row.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"https://127.0.0.1:{TEST_PORT}",
    ) as client:
        mut_headers = await _authenticate(client)
        yield client, mut_headers, tmp_path, project_id


def _make_unauthed_app(tmp_path: Path) -> Any:
    """Return a minimal FastAPI app for unauthenticated auth tests."""

    db_path = tmp_path / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()
    app = build_test_app(tmp_path, "tok", port=TEST_PORT)
    return app


async def _authed_client_for_config(tmp_path: Path, payload: dict[str, Any]):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(json.dumps(payload))

    db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ConnectionFactory(db_path).init_schema()

    app = build_test_app(tmp_path, HANDSHAKE, port=TEST_PORT)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(
        transport=transport,
        base_url=f"https://127.0.0.1:{TEST_PORT}",
    )
    await _authenticate(client)
    return client


class TestToolsCatalog:
    async def test_catalog_returns_items(self, app_client) -> None:
        client, *_ = app_client
        app = client._transport.app
        registry = app.state.tool_registry
        registry.clear()
        registry.register(_FakeTool("bandit", "sast", "Python security linter"))
        registry.register(_FakeTool("gitleaks", "secrets", "Secret scanner"))
        app.state.tool_catalog_snapshot = registry.snapshot()
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) == data["total"]
        ids = {item["id"] for item in data["items"]}
        assert "bandit" in ids
        assert "gitleaks" in ids

    async def test_catalog_item_fields(self, app_client) -> None:
        client, *_ = app_client
        app = client._transport.app
        registry = app.state.tool_registry
        registry.clear()
        registry.register(_FakeTool("bandit", "sast", "Python security linter"))
        app.state.tool_catalog_snapshot = registry.snapshot()
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["id"] == "bandit"
        assert item["name"] == "Bandit"
        assert item["domain"] == "sast"
        assert isinstance(item["supports_local"], bool)
        assert isinstance(item["supports_docker"], bool)
        assert item["description"] == "Python security linter"
        assert isinstance(item["requires_base_urls"], bool)
        assert isinstance(item["requires_url_inventory"], bool)
        assert isinstance(item["requires_arg_profile"], bool)

    async def test_catalog_with_empty_registry_only_has_disk_tools(
        self, app_client
    ) -> None:
        client, *_ = app_client
        app = client._transport.app
        registry = app.state.tool_registry
        registry.clear()
        app.state.tool_catalog_snapshot = registry.snapshot()
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == len(data["items"])
        for item in data["items"]:
            assert item["domain"] == ""

    async def test_catalog_stable_after_registry_mutation(self, app_client) -> None:
        client, *_ = app_client
        app = client._transport.app
        registry = app.state.tool_registry
        registry.clear()
        registry.register(_FakeTool("bandit", "sast", "Python linter"))
        registry.register(_FakeTool("gitleaks", "secrets", "Secret scanner"))
        app.state.tool_catalog_snapshot = registry.snapshot()
        registry.clear()
        resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code == 200
        data = resp.json()
        ids = {item["id"] for item in data["items"]}
        assert "bandit" in ids
        assert "gitleaks" in ids
        assert data["total"] == len(data["items"])

    async def test_catalog_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/tools/catalog")
        assert resp.status_code in (401, 403)


class TestInstalledTools:
    async def test_returns_only_available_tools(self, app_client) -> None:
        from infrastructure.system.installed_tools_probe import InstalledToolsProbe

        client, *_ = app_client
        registry = client._transport.app.state.tool_registry
        registry.clear()
        registry.register(_FakeTool("bandit", "sast", "Python linter", installed=True))
        registry.register(_FakeTool("nuclei", "dast", "Web scanner", installed=False))
        registry.register(
            _FakeTool("gitleaks", "secrets", "Secret scanner", installed=True)
        )
        client._transport.app.state.installed_tools = (  # type: ignore[attr-defined]
            InstalledToolsProbe(registry)
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
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/tools/installed")
        assert resp.status_code in (401, 403)


class TestRuntimeDependencies:
    async def test_returns_docker_probe(self, tmp_path: Path) -> None:
        client = await _authed_client_for_config(tmp_path, {})
        try:
            resp = await client.get("/api/v1/runtime-dependencies")
        finally:
            await client.aclose()
        assert resp.status_code == 200
        deps = resp.json()["dependencies"]
        assert len(deps) == 1
        assert deps[0]["name"] == "docker"

    async def test_docker_probe_with_claude_config(self, tmp_path: Path) -> None:
        client = await _authed_client_for_config(
            tmp_path,
            {"triage_agent_provider": "claude_code"},
        )
        try:
            resp = await client.get("/api/v1/runtime-dependencies")
        finally:
            await client.aclose()

        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["dependencies"]]
        assert "docker" in names

    async def test_docker_probe_with_open_code_config(self, tmp_path: Path) -> None:
        client = await _authed_client_for_config(
            tmp_path,
            {"triage_agent_provider": "open_code"},
        )
        try:
            resp = await client.get("/api/v1/runtime-dependencies")
        finally:
            await client.aclose()

        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["dependencies"]]
        assert "docker" in names

    async def test_requires_auth(self, tmp_path: Path) -> None:
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "global.json").write_text("{}")
        app = _make_unauthed_app(tmp_path)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"https://127.0.0.1:{TEST_PORT}",
        ) as client:
            resp = await client.get("/api/v1/runtime-dependencies")
        assert resp.status_code in (401, 403)
