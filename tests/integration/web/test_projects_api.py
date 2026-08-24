from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import RepoAuth, Repository
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.runs import RunRepository
from tests._app_factory import build_test_app
from tests.finding_helpers import normalize_test_findings

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
}


def _seed_repo() -> Repository:
    return Repository(
        name="test-repo",
        path="",
        services=[
            RepoService(
                name="default",
                type=["api"],
                docker_path="/app",
                container_name="test_container",
                languages=["python"],
                base_urls=["http://localhost"],
            )
        ],
        auth=RepoAuth(
            login_url="http://localhost/login",
            username="admin",
            password="super-secret-password",
        ),
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

    repo_repo = RepositoryRepository(factory)
    repo_repo.insert(_seed_repo())

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.insert_findings(run_id, normalize_test_findings([_BASE_FINDING]))

    kb_mock = MagicMock()
    kb_mock.get.return_value = [{"id": "doc-1", "metadata": {}}]

    app = build_test_app(tmp_path, _HANDSHAKE, port=_TEST_PORT)
    app.state.knowledge_base_cache = {"testproject": kb_mock}

    row = app.state.project_registry.resolve_by_name("testproject")
    assert row is not None
    project_id = row.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"https://127.0.0.1:{_TEST_PORT}",
    ) as client:
        mut_headers = await _auth(client)
        yield client, mut_headers, project_id


class TestListProjectsV1:
    async def test_list_projects_returns_registered_project(
        self, projects_v1_client
    ) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        items = resp.json()["items"]
        ids = [i["id"] for i in items]
        assert project_id in ids

    async def test_list_projects_pagination(self, projects_v1_client) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) == 1

    async def test_list_projects_returns_expected_fields(
        self, projects_v1_client
    ) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects")
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
        assert isinstance(data["enabled_tools"], list)

    async def test_project_meta_enabled_tools_sorted(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/meta")
        assert resp.status_code == 200
        tools = resp.json()["enabled_tools"]
        assert tools == sorted(tools)

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
            "company_name",
            "department_name",
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
        assert data["company_name"] == "New Co"
        assert data["department_name"] == "Engineering"
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
        assert data["company_name"] == "Only Co"
        assert data["department_name"] == "Security"
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
        assert data["company_name"] == "Acme Corp"
        assert data["department_name"] == "Security"
        assert data["abbreviation"] == "TP"


class TestCreateProjectV1:
    async def test_create_returns_201_with_all_fields(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={
                "name": "newproj",
                "company_name": "ACME",
                "department_name": "Infra",
                "abbreviation": "NP",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "newproj"
        assert data["code"] == "NP"
        assert isinstance(data["id"], int)
        assert "created_at" in data

    async def test_create_minimal_payload(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "minimal"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "minimal"
        assert data["code"] == ""

    async def test_create_duplicate_returns_409(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "testproject"},
            headers=headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    async def test_create_invalid_name_returns_422(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "!invalid!"},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_empty_name_returns_422(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={"name": ""},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_abbreviation_too_long_returns_422(
        self, projects_v1_client
    ) -> None:
        client, headers, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={
                "name": "longabbr",
                "abbreviation": "TOOLONG",
            },
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_appears_in_list(self, projects_v1_client) -> None:
        client, headers, _ = projects_v1_client
        create_resp = await client.post(
            "/api/v1/projects",
            json={"name": "listed"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        new_id = create_resp.json()["id"]

        list_resp = await client.get("/api/v1/projects")
        ids = [i["id"] for i in list_resp.json()["items"]]
        assert new_id in ids

    async def test_create_without_csrf_returns_403(self, projects_v1_client) -> None:
        client, _, _ = projects_v1_client
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "nocsrf"},
        )
        assert resp.status_code == 403


class TestRepositoriesV1:
    async def test_repositories_list_omits_auth(self, projects_v1_client) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        assert resp.status_code == 200
        raw = resp.text
        assert '"username"' not in raw
        assert '"password"' not in raw
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

    async def test_repository_detail_returns_repo_and_omits_auth(
        self, projects_v1_client
    ) -> None:
        client, _, project_id = projects_v1_client
        list_resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert items, "fixture should expose at least one repository"
        target = items[0]
        repo_id = target["id"]

        detail_resp = await client.get(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}"
        )
        assert detail_resp.status_code == 200
        raw = detail_resp.text
        assert '"username"' not in raw
        assert '"password"' not in raw
        assert "super-secret-password" not in raw

        body = detail_resp.json()
        assert body["id"] == repo_id
        assert body["name"] == target["name"]
        assert body["services"] == target["services"]

    async def test_repository_detail_unknown_project_returns_404(
        self, projects_v1_client
    ) -> None:
        client, _, _ = projects_v1_client
        resp = await client.get("/api/v1/projects/9999/repositories/1")
        assert resp.status_code == 404

    async def test_repository_detail_unknown_repo_returns_404(
        self, projects_v1_client
    ) -> None:
        client, _, project_id = projects_v1_client
        resp = await client.get(f"/api/v1/projects/{project_id}/repositories/9999")
        assert resp.status_code == 404

    async def test_repository_detail_soft_deleted_returns_404(
        self, projects_v1_client
    ) -> None:
        client, mut_headers, project_id = projects_v1_client
        list_resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        repo_id = list_resp.json()["items"][0]["id"]

        delete_resp = await client.delete(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            headers=mut_headers,
        )
        assert delete_resp.status_code == 204

        resp = await client.get(f"/api/v1/projects/{project_id}/repositories/{repo_id}")
        assert resp.status_code == 404
