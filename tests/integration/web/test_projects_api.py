from __future__ import annotations

import pytest

from tests.integration.web.conftest import AUTH

pytestmark = pytest.mark.integration


class TestGetProject:
    async def test_returns_project_name(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/projects/", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["project_name"] == "testproject"

    async def test_returns_sqlite_path(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/projects/", headers=AUTH)
        assert response.status_code == 200
        sqlite_path = response.json()["sqlite_path"]
        assert sqlite_path.endswith("projects/testproject/sqlite/findings.db")

    async def test_sqlite_path_uses_base_path(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/projects/", headers=AUTH)
        assert response.status_code == 200
        sqlite_path = response.json()["sqlite_path"]
        assert "projects/testproject/sqlite/findings.db" in sqlite_path

    async def test_requires_auth(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/projects/")
        assert response.status_code == 401
