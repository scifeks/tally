from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from web.server import create_app

pytestmark = pytest.mark.integration

_TEST_PORT = 12345
_HANDSHAKE = "test-handshake-abc123xyz"

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
    "profile": "testproject",
    "remediation": "old",
    "author": "jdoe",
    "commit": "abc123",
}

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
                "password": "super-secret-password",
            },
        }
    ],
}


async def _auth(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/auth/exchange",
        json={"token": _HANDSHAKE},
        headers={"origin": f"http://127.0.0.1:{_TEST_PORT}"},
    )
    assert resp.status_code == 200
    csrf_token = resp.json()["csrf_token"]
    for name, value in resp.cookies.items():
        client.cookies.delete(name, domain="127.0.0.1")
        client.cookies.set(name, value)
    return {
        "X-CSRF-Token": csrf_token,
        "Origin": f"http://127.0.0.1:{_TEST_PORT}",
    }


@pytest_asyncio.fixture()
async def projects_v1_client(tmp_path: Path):
    """Yield (client, mut_headers) with a real project config and seeded DB."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text("{}")

    proj_dir = tmp_path / "projects" / "testproject"
    (proj_dir / "config").mkdir(parents=True)
    (proj_dir / "config" / "project.json").write_text(json.dumps(_PROJECT_CONFIG))

    db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
    db_path.parent.mkdir(parents=True)
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, [_BASE_FINDING])

    rag_mock = MagicMock()
    rag_mock.get_documents = MagicMock(
        return_value={"ids": ["doc-1"], "metadatas": [{}]}
    )

    app = create_app(str(tmp_path), _HANDSHAKE, port=_TEST_PORT)
    app.state.rag_engine_cache = {"testproject": rag_mock}

    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = int(row["id"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{_TEST_PORT}",
    ) as client:
        mut_headers = await _auth(client)
        yield client, mut_headers, project_id


class TestListProjectsV1:
    async def test_list_projects_returns_registered_project(
        self, projects_v1_client
    ) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get("/api/v1/projects/")
        assert resp.status_code == 200
        items = resp.json()["items"]
        ids = [i["id"] for i in items]
        assert project_id in ids

    async def test_list_projects_pagination(self, projects_v1_client) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects/?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) == 1

    async def test_list_projects_returns_expected_fields(
        self, projects_v1_client
    ) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects/")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "id" in item
            assert isinstance(item["id"], int)
            assert "name" in item
            assert "code" in item
            assert "created_at" in item
            assert "is_active" not in item


class TestProjectMetaV1:
    async def test_project_meta_returns_counts(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == project_id
        assert data["repo_count"] >= 1
        assert data["finding_count"] >= 1

    async def test_project_meta_unknown_returns_404(self, projects_v1_client) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects/9999/meta")
        assert resp.status_code == 404


class TestProjectInfoV1:
    async def test_project_info_returns_full_fields(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == project_id
        for field in (
            "company",
            "department",
            "abbreviation",
            "path",
            "repo_count",
            "finding_count",
        ):
            assert field in data

    async def test_project_info_unknown_returns_404(self, projects_v1_client) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects/9999/info")
        assert resp.status_code == 404


class TestProjectInfoPatchV1:
    async def test_patch_updates_company_department_abbreviation(
        self, projects_v1_client
    ) -> None:
        client, headers, project_id = projects_v1_client
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/info",
            json={
                "company_name": "New Co",
                "department_name": "Engineering",
                "abbreviation": "NEW",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["company"] == "New Co"
        assert data["department"] == "Engineering"
        assert data["abbreviation"] == "NEW"
        # Persists across reads.
        resp2 = await client.get(f"/api/v1/projects/{project_id}/info")
        assert resp2.json()["abbreviation"] == "NEW"

    async def test_patch_partial_only_updates_provided_fields(
        self, projects_v1_client
    ) -> None:
        client, headers, project_id = projects_v1_client
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/info",
            json={"company_name": "Only Co"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company"] == "Only Co"
        assert data["department"] == "Security"
        assert data["abbreviation"] == "TP"

    async def test_patch_rejects_abbreviation_too_long(
        self, projects_v1_client
    ) -> None:
        client, headers, project_id = projects_v1_client
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/info",
            json={"abbreviation": "TOOLONG"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_patch_unknown_project_returns_404(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.patch(
            "/api/v1/projects/9999/info",
            json={"company_name": "X"},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_patch_without_csrf_returns_403(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/info",
            json={"company_name": "NoCSRF"},
        )
        assert resp.status_code == 403

    async def test_patch_empty_body_is_noop(self, projects_v1_client) -> None:
        client, headers, project_id = projects_v1_client
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/info",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company"] == "Acme Corp"
        assert data["department"] == "Security"
        assert data["abbreviation"] == "TP"


class TestRepositoriesV1:
    async def test_repositories_list_omits_auth(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        assert resp.status_code == 200
        raw = resp.text
        assert "auth" not in raw
        assert "super-secret-key" not in raw
        assert len(resp.json()["items"]) >= 1

    async def test_repositories_list_pagination(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/repositories?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) == 1

    async def test_repositories_list_unknown_project_returns_404(
        self, projects_v1_client
    ) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects/9999/repositories")
        assert resp.status_code == 404
