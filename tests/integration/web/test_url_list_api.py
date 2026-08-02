"""Integration tests for URL list endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import Repository
from domain.url_inventory.entry import UrlFinding, UrlSource
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.url_findings import UrlFindingRepository
from tests._app_factory import build_test_app

pytestmark = pytest.mark.integration

_TEST_PORT = 12349
_HANDSHAKE = "test-handshake-abc123xyz"


def _project_config() -> dict[str, Any]:
    return {
        "project_name": "Test Project",
        "created": "2024-01-01T00:00:00",
        "abbreviation": "TP",
        "company_name": "Acme Corp",
        "department_name": "Security",
    }


def _seed_repo(repo_path: str) -> Repository:
    return Repository(
        name="alpha",
        path=repo_path,
        services=[
            RepoService(
                name="default",
                type=["api"],
                languages=["python"],
                base_urls=["http://localhost"],
            )
        ],
    )


async def _auth(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/exchange",
        json={"token": _HANDSHAKE},
        headers={"origin": f"https://127.0.0.1:{_TEST_PORT}"},
    )
    assert resp.status_code == 200
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    csrf_token = client.cookies["tally_csrf"]
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": f"https://127.0.0.1:{_TEST_PORT}",
    }


@pytest_asyncio.fixture()
async def url_list_client(tmp_path: Path):
    """Yield (client, mut_headers, project_id, repo_id)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text("{}")

    repo_path = tmp_path / "repo-src"
    repo_path.mkdir()

    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    (proj_dir / "config" / "project.json").write_text(json.dumps(_project_config()))

    db_path = proj_dir / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    rr = RepositoryRepository(factory)
    repo_id = rr.insert(_seed_repo(str(repo_path)))

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

    app = build_test_app(tmp_path, _HANDSHAKE, port=_TEST_PORT)
    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = row.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"https://127.0.0.1:{_TEST_PORT}",
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

    async def test_list_search_matches_method_and_repo_name(
        self, url_list_client
    ) -> None:
        client, _, project_id, _ = url_list_client
        # Method match: only the POST row
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?search=POST"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        # Repo-name match: "alpha" is the seeded repo name → all 3 rows
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?search=alpha"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    async def test_list_pagination(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?limit=1&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 1

    async def test_list_filter_by_method_multi_value(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries?method=GET&method=POST"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

    async def test_list_filter_by_protocol_host_port_path(
        self, url_list_client
    ) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/entries"
            "?protocol=https&host=api.example.com&port=443&path=/api/orders"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["path"] == "/api/orders"


class TestUrlListFilterOptions:
    async def test_no_filters_returns_all_dims(self, url_list_client) -> None:
        client, _, project_id, repo_id = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "method",
            "protocol",
            "host",
            "port",
            "path",
            "repo",
        }
        method_values = {item["value"]: item["count"] for item in data["method"]}
        assert method_values == {"GET": 2, "POST": 1}
        assert data["protocol"] == [{"value": "https", "count": 3}]
        assert data["port"] == [{"value": 443, "count": 3}]
        assert data["repo"] == [{"value": repo_id, "label": "alpha", "count": 3}]

    async def test_method_filter_narrows_other_dims(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options?method=POST"
        )
        assert resp.status_code == 200
        data = resp.json()
        # Strict semantics: method dim only shows POST.
        assert data["method"] == [{"value": "POST", "count": 1}]
        # Other dims also reflect the POST filter.
        path_values = {item["value"]: item["count"] for item in data["path"]}
        assert path_values == {"/api/users": 1}

    async def test_combined_filters_intersect(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options"
            "?method=GET&path=/api/orders"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == [{"value": "GET", "count": 1}]
        assert data["path"] == [{"value": "/api/orders", "count": 1}]

    async def test_no_match_returns_empty_arrays(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options"
            "?host=nowhere.invalid"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "method": [],
            "protocol": [],
            "host": [],
            "port": [],
            "path": [],
            "repo": [],
        }

    async def test_port_returns_int_type(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options"
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["port"]:
            assert isinstance(item["value"], int)

    async def test_repo_filter_param(self, url_list_client) -> None:
        client, _, project_id, repo_id = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options?repo_id={repo_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo"] == [{"value": repo_id, "label": "alpha", "count": 3}]

    async def test_invalid_port_returns_422(self, url_list_client) -> None:
        client, _, project_id, _ = url_list_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/url-list/filter-options?port=abc"
        )
        assert resp.status_code == 422

    async def test_unknown_project_returns_404(self, url_list_client) -> None:
        client, _, _, _ = url_list_client
        resp = await client.get("/api/v1/projects/99999/url-list/filter-options")
        assert resp.status_code == 404


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
