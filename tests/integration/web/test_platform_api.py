"""Integration tests for platform endpoints (/api/v1/health)."""

from __future__ import annotations

import sqlite3
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from web.server import create_app

pytestmark = pytest.mark.integration

_TEST_PORT = 12347
_HANDSHAKE = "test-handshake-platform"


@pytest_asyncio.fixture()
async def platform_client(tmp_path: Path):
    """Yield (client, app) on a bare base_path (no projects required)."""
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "global.json").write_text("{}")

    app = create_app(str(tmp_path), _HANDSHAKE, port=_TEST_PORT)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{_TEST_PORT}",
    ) as client:
        yield client, app


class TestHealth:
    async def test_health_returns_ok_without_auth(self, platform_client) -> None:
        client, _ = platform_client
        # No handshake exchange, no session cookie; endpoint must still respond.
        resp = await client.get(
            "/api/v1/health",
            headers={"Origin": f"http://127.0.0.1:{_TEST_PORT}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert isinstance(body["version"], str) and body["version"]

    async def test_health_version_matches_package(self, platform_client) -> None:
        client, _ = platform_client
        resp = await client.get(
            "/api/v1/health",
            headers={"Origin": f"http://127.0.0.1:{_TEST_PORT}"},
        )
        assert resp.status_code == 200
        try:
            expected = version("tally")
        except PackageNotFoundError:
            expected = "0.0.0"
        assert resp.json()["version"] == expected

    async def test_health_returns_503_when_db_unavailable(
        self, platform_client, monkeypatch
    ) -> None:
        client, app = platform_client

        def _boom() -> None:
            raise sqlite3.OperationalError("simulated registry failure")

        monkeypatch.setattr(app.state.project_registry, "ping", _boom)

        resp = await client.get(
            "/api/v1/health",
            headers={"Origin": f"http://127.0.0.1:{_TEST_PORT}"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["db"] == "error"
        assert isinstance(body["version"], str) and body["version"]
