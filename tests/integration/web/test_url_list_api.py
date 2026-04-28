"""Integration tests for URL list endpoints (Phase 9.5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from domain.url_inventory.entry import UrlFinding, UrlSource
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.url_findings import UrlFindingRepository
from web.server import create_app

pytestmark = pytest.mark.integration

_TEST_PORT = 12349
_HANDSHAKE = "test-handshake-abc123xyz"


def _project_config_with_repo(repo_uuid: str, repo_path: str) -> dict[str, Any]:
    return {
        "project_name": "Test Project",
        "created": "2024-01-01T00:00:00",
        "abbreviation": "TP",
        "company_name": "Acme Corp",
        "department_name": "Security",
        "repositories": [
            {
                "name": "alpha",
                "uuid": repo_uuid,
                "type": ["api"],
                "path": repo_path,
                "languages": ["python"],
                "base_urls": ["http://localhost"],
            }
        ],
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
async def url_list_client(tmp_path: Path):
    """Yield (client, mut_headers, project_id, repo_id)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text("{}")

    repo_uuid = str(uuid4())
    repo_path = tmp_path / "repo-src"
    repo_path.mkdir()

    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    (proj_dir / "config" / "project.json").write_text(
        json.dumps(_project_config_with_repo(repo_uuid, str(repo_path)))
    )

    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    rr = RepositoryRepository(factory)
    repo_id = rr.insert(uuid=repo_uuid, name="alpha")

    ufr = UrlFindingRepository(factory)
    ufr.insert_many(
        [
            UrlFinding(
                repo_id=repo_id,
                source=UrlSource.USER,
                tool=None,
                run_id=None,
                method="GET",
                protocol="https",
                host="api.example.com",
                port=443,
                path="/api/users",
                file_path="/uploads/spec.json",
            ),
            UrlFinding(
                repo_id=repo_id,
                source=UrlSource.USER,
                tool=None,
                run_id=None,
                method="POST",
                protocol="https",
                host="api.example.com",
                port=443,
                path="/api/users",
                file_path="/uploads/spec.json",
            ),
            UrlFinding(
                repo_id=repo_id,
                source=UrlSource.USER,
                tool=None,
                run_id=None,
                method="GET",
                protocol="https",
                host="api.example.com",
                port=443,
                path="/api/orders",
                file_path="/uploads/spec.json",
            ),
        ]
    )

    app = create_app(str(tmp_path), _HANDSHAKE, port=_TEST_PORT)
    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = int(row["id"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{_TEST_PORT}",
    ) as client:
        mut_headers = await _auth(client)
        yield client, mut_headers, project_id, repo_id


class TestListEntries:
    async def test_list_returns_all_entries_with_repo_name(
        self, url_list_client
    ) -> None:
        client, _, project_id, repo_id = url_list_client
        resp = await client.get(f"/api/v1/projects/{project_id}/url-list/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        for item in data["items"]:
            assert item["repo_id"] == repo_id
            assert item["repo_name"] == "alpha"
            assert item["project_id"] == project_id

    async def test_list_filter_by_method(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?method=POST"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["method"] == "POST"

    async def test_list_search_by_path(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?search=orders"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["path"] == "/api/orders"

    async def test_list_pagination(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?limit=1&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 1


class TestExport:
    async def test_export_json(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/export?format=json"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        rows = json.loads(resp.text)
        assert len(rows) == 3

    async def test_export_csv(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/export?format=csv"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        # Header + 3 rows.
        lines = [line for line in resp.text.splitlines() if line]
        assert len(lines) == 4
        assert "repo_name" in lines[0]

    async def test_export_txt(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/export?format=txt"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "https://api.example.com:443/api/users" in resp.text

    async def test_export_invalid_format_returns_422(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/export?format=xml"
        )
        assert resp.status_code == 422


class TestRegenerate:
    async def test_regenerate_writes_artifacts(self, url_list_client) -> None:
        client, headers, project_id, repo_id = url_list_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/url-list/regenerate",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["regenerated"]) == 1
        item = body["regenerated"][0]
        assert item["repo_id"] == repo_id
        assert Path(item["seeds_path"]).exists()
        assert Path(item["oas3_path"]).exists()


class TestMetaUrlListCount:
    async def test_meta_returns_real_url_count(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(f"/api/v1/projects/{project_id}/meta")
        assert resp.status_code == 200
        assert resp.json()["url_list_count"] == 3
