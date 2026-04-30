"""Integration tests for repository CRUD endpoints (Phase 9.3)."""

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

_TEST_PORT = 12347
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
async def repo_crud_client(tmp_path: Path):
    """Yield (client, mut_headers, project_id, repo_path)."""
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

    repo_path = tmp_path / "repo-src"
    repo_path.mkdir()

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
        yield client, mut_headers, project_id, str(repo_path)


def _basic_payload(name: str, path: str) -> str:
    return json.dumps(
        {
            "name": name,
            "type": ["api"],
            "path": path,
            "languages": ["python"],
            "base_urls": ["http://localhost"],
        }
    )


class TestCreateRepository:
    async def test_create_returns_201_with_uuid_and_id(self, repo_crud_client) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("alpha", repo_path)},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "alpha"
        assert data["uuid"]
        assert isinstance(data["id"], int)
        assert "auth" not in data

    async def test_create_persists_in_list(self, repo_crud_client) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("beta", repo_path)},
            headers=headers,
        )
        resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()["items"]]
        assert "beta" in names

    async def test_create_rejects_duplicate_name(self, repo_crud_client) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("dup", repo_path)},
            headers=headers,
        )
        resp = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("dup", repo_path)},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_rejects_missing_path(self, repo_crud_client) -> None:
        client, headers, project_id, _ = repo_crud_client
        payload = json.dumps(
            {"name": "bad", "type": ["api"], "path": "/nonexistent/xyz/abc"}
        )
        resp = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": payload},
            headers=headers,
        )
        assert resp.status_code == 422

    async def test_create_without_csrf_returns_403(self, repo_crud_client) -> None:
        client, _, project_id, repo_path = repo_crud_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("x", repo_path)},
        )
        assert resp.status_code == 403


class TestPatchRepository:
    async def test_patch_renames_repo(self, repo_crud_client) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("orig", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            data={"payload": json.dumps({"name": "renamed"})},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "renamed"
        # List reflects rename.
        list_resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        names = [r["name"] for r in list_resp.json()["items"]]
        assert "renamed" in names
        assert "orig" not in names

    async def test_patch_unknown_repo_returns_404(self, repo_crud_client) -> None:
        client, headers, project_id, _ = repo_crud_client
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/repositories/9999",
            data={"payload": json.dumps({"name": "x"})},
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_patch_name_only_does_not_modify_json(
        self, repo_crud_client, tmp_path: Path
    ) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("name-test", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]

        json_path = tmp_path / "projects" / "testproject" / "config" / "project.json"
        content_before = json_path.read_text()
        mtime_before = json_path.stat().st_mtime_ns

        resp = await client.patch(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            data={"payload": json.dumps({"name": "name-only-rename"})},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "name-only-rename"
        assert json_path.read_text() == content_before
        assert json_path.stat().st_mtime_ns == mtime_before

    async def test_patch_non_name_field_updates_json(
        self, repo_crud_client, tmp_path: Path
    ) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("field-test", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]

        json_path = tmp_path / "projects" / "testproject" / "config" / "project.json"
        mtime_before = json_path.stat().st_mtime_ns

        resp = await client.patch(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            data={
                "payload": json.dumps(
                    {"name": "field-test", "base_urls": ["http://updated"]}
                )
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert json_path.stat().st_mtime_ns != mtime_before
        saved = json.loads(json_path.read_text())
        repo_entry = next(r for r in saved["repositories"] if r["name"] == "field-test")
        assert "http://updated" in repo_entry["base_urls"]


class TestDeleteRepository:
    async def test_delete_soft_removes_from_list(self, repo_crud_client) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("doomed", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            headers=headers,
        )
        assert resp.status_code == 204
        list_resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        names = [r["name"] for r in list_resp.json()["items"]]
        assert "doomed" not in names

    async def test_delete_unknown_returns_404(self, repo_crud_client) -> None:
        client, headers, project_id, _ = repo_crud_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/repositories/9999",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_delete_idempotent_second_call_returns_404(
        self, repo_crud_client
    ) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("twice", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]
        first = await client.delete(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            headers=headers,
        )
        assert first.status_code == 204
        second = await client.delete(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}",
            headers=headers,
        )
        assert second.status_code == 404


class TestRepositoryEndpointFileMultipart:
    """POST and PATCH with the optional ``endpoint_file`` upload (Phase 9.3).

    The single multipart surface covers the role of the dropped
    ``POST /endpoint-file`` and ``POST /url-list/import`` routes:
    uploading an OAS3 / HAR / Postman / Swagger file copies it into
    ``endpoints/<repo.uuid>/user_uploads/`` and ingests its rows into
    ``url_findings`` via ``UserFileProvider``.
    """

    @staticmethod
    def _oas3_with_path(path: str) -> bytes:
        return json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "t", "version": "1"},
                "paths": {path: {"get": {"responses": {"200": {"description": ""}}}}},
            }
        ).encode("utf-8")

    @staticmethod
    def _row_count(tmp_path: Path, repo_uuid: str) -> int:
        from infrastructure.store.repositories.repositories import (
            RepositoryRepository,
        )
        from infrastructure.store.repositories.url_findings import (
            UrlFindingRepository,
        )

        db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
        if not db_path.exists():
            return 0
        factory = ConnectionFactory(db_path)
        repo_row = RepositoryRepository(factory).get_by_uuid(repo_uuid)
        if repo_row is None:
            return 0
        return len(UrlFindingRepository(factory).list_for_repo(repo_row.id))

    async def test_post_with_endpoint_file_seeds_url_findings(
        self, repo_crud_client, tmp_path: Path
    ) -> None:
        """POST with multipart ``endpoint_file`` ingests rows + writes upload."""
        client, headers, project_id, repo_path = repo_crud_client
        files = {
            "payload": (None, _basic_payload("with-file", repo_path)),
            "endpoint_file": (
                "api.json",
                self._oas3_with_path("/users"),
                "application/json",
            ),
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            files=files,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        repo = resp.json()
        assert repo["uuid"]
        assert self._row_count(tmp_path, repo["uuid"]) == 1
        upload = (
            tmp_path
            / "projects"
            / "testproject"
            / "endpoints"
            / repo["uuid"]
            / "user_uploads"
            / "api.json"
        )
        assert upload.exists()
        assert repo["endpoint_file"] == "api.json"

    async def test_patch_endpoint_file_replaces_rows(
        self, repo_crud_client, tmp_path: Path
    ) -> None:
        """PATCH with new ``endpoint_file`` wipes prior USER rows for that file."""
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            files={
                "payload": (None, _basic_payload("file-edit", repo_path)),
                "endpoint_file": (
                    "first.json",
                    self._oas3_with_path("/old"),
                    "application/json",
                ),
            },
            headers=headers,
        )
        assert post.status_code == 201
        repo = post.json()
        assert self._row_count(tmp_path, repo["uuid"]) == 1

        patch = await client.patch(
            f"/api/v1/projects/{project_id}/repositories/{repo['id']}",
            files={
                "payload": (None, json.dumps({})),
                "endpoint_file": (
                    "second.json",
                    self._oas3_with_path("/new"),
                    "application/json",
                ),
            },
            headers=headers,
        )
        assert patch.status_code == 200, patch.text

        # Replacement is per file_path, so /old (from first.json) survives
        # alongside /new (from second.json) — but the new file is on disk.
        # Total rows ≥ 1; the new path must be present.
        from infrastructure.store.repositories.repositories import (
            RepositoryRepository,
        )
        from infrastructure.store.repositories.url_findings import (
            UrlFindingRepository,
        )

        db_path = tmp_path / "projects" / "testproject" / "sqlite" / "findings.db"
        factory = ConnectionFactory(db_path)
        db_row = RepositoryRepository(factory).get_by_uuid(repo["uuid"])
        assert db_row is not None
        rows = UrlFindingRepository(factory).list_for_repo(db_row.id)
        paths = sorted({r.path for r in rows})
        assert "/new" in paths
        # The new upload exists under user_uploads/.
        upload = (
            tmp_path
            / "projects"
            / "testproject"
            / "endpoints"
            / repo["uuid"]
            / "user_uploads"
            / "second.json"
        )
        assert upload.exists()
        assert patch.json()["endpoint_file"] == "second.json"

    async def test_get_repository_detail_returns_endpoint_file_when_present(
        self, repo_crud_client
    ) -> None:
        """GET detail surfaces the basename of the user-uploaded file."""
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            files={
                "payload": (None, _basic_payload("with-seed", repo_path)),
                "endpoint_file": (
                    "spec.json",
                    self._oas3_with_path("/x"),
                    "application/json",
                ),
            },
            headers=headers,
        )
        assert post.status_code == 201, post.text
        repo_id = post.json()["id"]

        resp = await client.get(f"/api/v1/projects/{project_id}/repositories/{repo_id}")
        assert resp.status_code == 200
        assert resp.json()["endpoint_file"] == "spec.json"

        list_resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        assert list_resp.status_code == 200
        item = next(r for r in list_resp.json()["items"] if r["id"] == repo_id)
        assert item["endpoint_file"] == "spec.json"

    async def test_get_repository_detail_returns_null_when_no_upload(
        self, repo_crud_client
    ) -> None:
        """GET detail returns ``endpoint_file: None`` for a bare repo."""
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("bare", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]
        assert post.json()["endpoint_file"] is None

        resp = await client.get(f"/api/v1/projects/{project_id}/repositories/{repo_id}")
        assert resp.status_code == 200
        assert resp.json()["endpoint_file"] is None


class TestPatchRepositoryAuth:
    async def test_patch_auth_returns_204_and_does_not_echo(
        self, repo_crud_client
    ) -> None:
        client, headers, project_id, repo_path = repo_crud_client
        post = await client.post(
            f"/api/v1/projects/{project_id}/repositories",
            data={"payload": _basic_payload("authed", repo_path)},
            headers=headers,
        )
        repo_id = post.json()["id"]
        resp = await client.patch(
            f"/api/v1/projects/{project_id}/repositories/{repo_id}/auth",
            json={
                "login_url": "http://localhost/login",
                "username": "admin",
                "password": "supersecret",
            },
            headers=headers,
        )
        assert resp.status_code == 204
        list_resp = await client.get(f"/api/v1/projects/{project_id}/repositories")
        for item in list_resp.json()["items"]:
            assert "auth" not in item
            assert "password" not in json.dumps(item)
