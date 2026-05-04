"""Integration tests for tool override routes."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_LOCAL_BODY = {
    "toolName": "semgrep",
    "argsMode": "stock",
    "type": "repo",
    "location": "local",
    "path": "/usr/local/bin/semgrep",
}
_DOCKER_BODY = {
    "toolName": "gitleaks",
    "argsMode": "custom",
    "type": "repo",
    "location": "docker",
    "container": {"name": "tally-gitleaks", "toolPath": "/usr/local/bin/gitleaks"},
}


class TestToolOverridesRoutes:
    async def test_get_returns_empty_envelope_when_no_overrides(self, app_client):
        client, _, _, _, _, project_id = app_client
        resp = await client.get(f"/api/v1/projects/{project_id}/tools/overrides")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    async def test_post_creates_local_override_returns_201_and_camel_case(
        self, app_client
    ):
        client, _, _, factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["toolName"] == "semgrep"
        assert data["argsMode"] == "stock"
        assert data["type"] == "repo"
        assert data["location"] == "local"
        assert data["path"] == "/usr/local/bin/semgrep"
        assert data["container"] is None
        assert "id" in data

    async def test_post_creates_docker_override_with_container(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_DOCKER_BODY,
            headers=mut_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["toolName"] == "gitleaks"
        assert data["location"] == "docker"
        assert data["container"] is not None
        assert data["container"]["name"] == "tally-gitleaks"
        assert data["container"]["toolPath"] == "/usr/local/bin/gitleaks"

    async def test_post_emits_camel_case_response_keys(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_DOCKER_BODY,
            headers=mut_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "toolName" in data
        assert "argsMode" in data
        assert "tool_name" not in data
        assert "args_mode" not in data
        if data.get("container"):
            assert "toolPath" in data["container"]
            assert "tool_path" not in data["container"]

    async def test_post_local_without_path_returns_422_with_fields_envelope(
        self, app_client
    ):
        client, _, _, factory, mut_headers, project_id = app_client
        body = {
            "toolName": "semgrep",
            "argsMode": "stock",
            "type": "repo",
            "location": "local",
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "fields" in data["error"]["details"]
        assert len(data["error"]["details"]["fields"]) > 0

    async def test_post_docker_without_container_returns_422(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        body = {
            "toolName": "gitleaks",
            "argsMode": "custom",
            "type": "repo",
            "location": "docker",
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "fields" in data["error"]["details"]

    async def test_post_invalid_args_mode_returns_422(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        body = {
            "toolName": "semgrep",
            "argsMode": "bogus",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/semgrep",
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422

    async def test_post_duplicate_tool_name_returns_409(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"]["code"] == "CONFLICT"

    async def test_post_without_csrf_returns_403(self, app_client):
        client, _, _, factory, _, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
        )
        assert resp.status_code == 403

    async def test_post_unknown_project_returns_404(self, app_client):
        client, _, _, factory, mut_headers, _ = app_client
        resp = await client.post(
            "/api/v1/projects/999999/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_get_after_post_lists_the_new_row(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        resp = await client.get(f"/api/v1/projects/{project_id}/tools/overrides")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["toolName"] == "semgrep"

    async def test_get_pagination_offset_limit_respected(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        bodies = [
            {
                "toolName": "semgrep",
                "argsMode": "stock",
                "type": "repo",
                "location": "local",
                "path": "/usr/local/bin/semgrep",
            },
            {
                "toolName": "gitleaks",
                "argsMode": "custom",
                "type": "repo",
                "location": "docker",
                "container": {
                    "name": "tally-gitleaks",
                    "toolPath": "/usr/local/bin/gitleaks",
                },
            },
            {
                "toolName": "trivy",
                "argsMode": "stock",
                "type": "repo",
                "location": "local",
                "path": "/usr/local/bin/trivy",
            },
        ]
        for body in bodies:
            await client.post(
                f"/api/v1/projects/{project_id}/tools/overrides",
                json=body,
                headers=mut_headers,
            )
        resp = await client.get(
            f"/api/v1/projects/{project_id}/tools/overrides?offset=1&limit=1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["offset"] == 1
        assert data["limit"] == 1
        assert len(data["items"]) == 1
        assert data["total"] == 3

    async def test_put_replaces_override_and_returns_200(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        new_body = {
            "argsMode": "custom",
            "type": "repo",
            "location": "local",
            "path": "/new/path/semgrep",
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep",
            json=new_body,
            headers=mut_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "/new/path/semgrep"
        assert data["argsMode"] == "custom"

    async def test_put_with_matching_tool_name_in_body_succeeds(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        new_body = {
            "toolName": "semgrep",
            "argsMode": "custom",
            "type": "repo",
            "location": "local",
            "path": "/new/path/semgrep",
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep",
            json=new_body,
            headers=mut_headers,
        )
        assert resp.status_code == 200

    async def test_put_with_mismatched_tool_name_in_body_returns_422(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        new_body = {
            "toolName": "different-tool",
            "argsMode": "custom",
            "type": "repo",
            "location": "local",
            "path": "/new/path/semgrep",
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep",
            json=new_body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        fields = data["error"]["details"]["fields"]
        assert any(f["field"] == "toolName" for f in fields)
        assert any("match" in f.get("issue", "").lower() for f in fields)

    async def test_put_unknown_tool_name_returns_404(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        body = {
            "argsMode": "custom",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/bogus",
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/bogus",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_put_without_csrf_returns_403(self, app_client):
        client, _, _, factory, _, project_id = app_client
        body = {
            "argsMode": "custom",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/semgrep",
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep",
            json=body,
        )
        assert resp.status_code == 403

    async def test_delete_removes_row_returns_204(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep",
            headers=mut_headers,
        )
        assert resp.status_code == 204
        get_resp = await client.get(f"/api/v1/projects/{project_id}/tools/overrides")
        assert get_resp.json()["total"] == 0

    async def test_delete_unknown_tool_name_returns_404(self, app_client):
        client, _, _, factory, mut_headers, project_id = app_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/bogus",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_delete_without_csrf_returns_403(self, app_client):
        client, _, _, factory, _, project_id = app_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep"
        )
        assert resp.status_code == 403

    async def test_post_refreshes_registry_with_db_overrides(
        self, app_client, monkeypatch
    ):
        client, _, _, factory, mut_headers, project_id = app_client
        calls = []

        def spy(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})

        monkeypatch.setattr("web.api.tools.discover_tools", spy)
        resp = await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        assert resp.status_code == 201
        assert len(calls) > 0
        assert calls[-1]["kwargs"].get("overrides_repo") is not None
        assert calls[-1]["kwargs"].get("project_name") == "testproject"

    async def test_delete_refreshes_registry(self, app_client, monkeypatch):
        client, _, _, factory, mut_headers, project_id = app_client
        await client.post(
            f"/api/v1/projects/{project_id}/tools/overrides",
            json=_LOCAL_BODY,
            headers=mut_headers,
        )
        calls = []

        def spy(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})

        monkeypatch.setattr("web.api.tools.discover_tools", spy)
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/tools/overrides/semgrep",
            headers=mut_headers,
        )
        assert resp.status_code == 204
        assert len(calls) > 0
