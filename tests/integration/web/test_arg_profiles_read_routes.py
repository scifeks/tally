"""Integration tests for arg-profile read routes (GET list and detail)."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.tool_arg_profiles.entry import (
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)
from infrastructure.storage.arg_files import ArgFilesStorageAdapter
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


class TestArgProfilesList:
    """Tests for GET /api/v1/projects/{project_id}/arg-profiles."""

    async def test_get_returns_empty_envelope_when_no_profiles(
        self, app_client
    ) -> None:
        """GET with no seeded profiles returns empty list envelope."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client
        resp = await client.get(f"/api/v1/projects/{project_id}/arg-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    async def test_get_lists_seeded_profile_in_camel_case(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET lists a seeded profile with camelCase fields."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(tool_name="gitleaks", name="verbose", args=[])

        resp = await client.get(f"/api/v1/projects/{project_id}/arg-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["toolName"] == "gitleaks"
        assert data["items"][0]["name"] == "verbose"

    async def test_get_filters_by_tool_name_query_param(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET with tool_name filter lists only matching profiles."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(tool_name="gitleaks", name="profile1", args=[])
        repo.insert(tool_name="semgrep", name="profile2", args=[])

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles?tool_name=gitleaks"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["toolName"] == "gitleaks"

    async def test_get_pagination_offset_limit_respected(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET with offset and limit respects pagination."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(tool_name="gitleaks", name="p1", args=[])
        repo.insert(tool_name="gitleaks", name="p2", args=[])
        repo.insert(tool_name="gitleaks", name="p3", args=[])

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles?offset=1&limit=1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3
        assert data["offset"] == 1
        assert data["limit"] == 1

    async def test_get_unknown_project_returns_404(self, app_client) -> None:
        """GET with unknown project ID returns 404 NOT_FOUND."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, _project_id = app_client
        resp = await client.get("/api/v1/projects/999999/arg-profiles")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_get_list_does_not_include_download_url(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET list response does not include downloadUrl for file args."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(
            tool_name="gitleaks",
            name="with-file",
            args=[
                ToolArgProfileFileArg(name="--rules", path="arg_files/1/--rules"),
            ],
        )

        resp = await client.get(f"/api/v1/projects/{project_id}/arg-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert len(item["args"]) == 1
        file_arg = item["args"][0]
        assert file_arg["name"] == "--rules"
        assert file_arg.get("downloadUrl") is None


class TestArgProfilesDetail:
    """Tests for GET /api/v1/projects/{project_id}/arg-profiles/{profile_id}."""

    async def test_get_unknown_profile_returns_404(self, app_client) -> None:
        """GET detail with unknown profile ID returns 404."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client
        resp = await client.get(f"/api/v1/projects/{project_id}/arg-profiles/999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_get_detail_returns_profile_in_camel_case(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET detail returns profile with camelCase and correct args."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(
            tool_name="gitleaks",
            name="detailed",
            args=[
                ToolArgProfileFlagArg(name="--verbose"),
                ToolArgProfileStringArg(name="--config", value="/etc/config"),
            ],
        )

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["toolName"] == "gitleaks"
        assert data["name"] == "detailed"
        assert len(data["args"]) == 2
        assert data["args"][0]["type"] == "flag"
        assert data["args"][0]["name"] == "--verbose"
        assert data["args"][1]["type"] == "string"
        assert data["args"][1]["name"] == "--config"
        assert data["args"][1]["value"] == "/etc/config"

    async def test_get_detail_populates_download_url_for_file_args(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET detail includes downloadUrl for file args with real files."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id_to_update = repo.insert(
            tool_name="gitleaks", name="with-file", args=[]
        )

        arg_files_dir = tmp_path / "projects" / "testproject" / "arg_files"
        arg_files_dir.mkdir(parents=True, exist_ok=True)
        storage = ArgFilesStorageAdapter(arg_files_dir)

        # Write a file to storage, then update the profile with its path
        path = storage.write(profile_id_to_update, "--rules", b"test-rules-content")
        file_arg = ToolArgProfileFileArg(name="--rules", path=path)
        repo.update(
            profile_id_to_update,
            tool_name="gitleaks",
            name="with-file",
            args=[file_arg],
        )

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id_to_update}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["args"]) == 1
        file_arg_resp = data["args"][0]
        assert file_arg_resp["name"] == "--rules"
        assert file_arg_resp["type"] == "file"
        assert file_arg_resp["downloadUrl"] is not None
        assert file_arg_resp["downloadUrl"].endswith(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id_to_update}/files/--rules"
        )

    async def test_get_detail_unknown_project_returns_404(self, app_client) -> None:
        """GET detail with unknown project ID returns 404."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, _project_id = app_client
        resp = await client.get("/api/v1/projects/999999/arg-profiles/1")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"
