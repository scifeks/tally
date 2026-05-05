"""Integration tests for the arg-profile file download route."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.tool_arg_profiles.entry import ToolArgProfileFileArg
from infrastructure.storage.arg_files import ArgFilesStorageAdapter
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _seed_profile_with_file(factory, tmp_path: Path, arg_name: str, data: bytes) -> int:
    """Insert a profile with one file arg and write its bytes; return profile_id."""
    repo = ToolArgProfilesRepository(factory)
    profile_id = repo.insert(tool_name="gitleaks", name="dl", args=[])
    arg_files_dir = tmp_path / "projects" / "testproject" / "arg_files"
    arg_files_dir.mkdir(parents=True, exist_ok=True)
    storage = ArgFilesStorageAdapter(arg_files_dir)
    path = storage.write(profile_id, arg_name, data)
    repo.update(
        profile_id,
        tool_name="gitleaks",
        name="dl",
        args=[ToolArgProfileFileArg(name=arg_name, path=path)],
    )
    return profile_id


class TestArgProfilesDownload:
    """Tests for GET /api/v1/projects/{project_id}/arg-profiles/{id}/files/{name}."""

    async def test_download_returns_bytes(self, app_client, tmp_path: Path) -> None:
        """GET returns 200 with the exact bytes that were written."""
        client, _f, _kb, factory, _h, project_id = app_client
        payload = b"rules-content-bytes"
        profile_id = _seed_profile_with_file(factory, tmp_path, "--rules", payload)

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}/files/--rules"
        )
        assert resp.status_code == 200
        assert resp.content == payload

    async def test_download_content_type_is_octet_stream(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET sets Content-Type to application/octet-stream."""
        client, _f, _kb, factory, _h, project_id = app_client
        profile_id = _seed_profile_with_file(factory, tmp_path, "--rules", b"x")

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}/files/--rules"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/octet-stream")

    async def test_download_content_disposition_is_inline_with_filename(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET sets Content-Disposition to inline with the arg name as filename."""
        client, _f, _kb, factory, _h, project_id = app_client
        profile_id = _seed_profile_with_file(factory, tmp_path, "--rules", b"x")

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}/files/--rules"
        )
        assert resp.status_code == 200
        assert resp.headers["content-disposition"] == 'inline; filename="--rules"'

    async def test_download_unknown_project_returns_404(self, app_client) -> None:
        """GET on a missing project returns 404 NOT_FOUND."""
        client, _f, _kb, _factory, _h, _project_id = app_client
        resp = await client.get("/api/v1/projects/999999/arg-profiles/1/files/--rules")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_download_unknown_profile_returns_404(self, app_client) -> None:
        """GET on a missing profile id returns 404 NOT_FOUND."""
        client, _f, _kb, _factory, _h, project_id = app_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/999/files/--rules"
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_download_unknown_arg_name_on_known_profile_returns_404(
        self, app_client
    ) -> None:
        """GET for an arg name with no stored file returns 404 NOT_FOUND."""
        client, _f, _kb, factory, _h, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="dl", args=[])

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}/files/--rules"
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_download_dotdot_arg_name_returns_400_path_traversal(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET with `..` arg name is rejected at the storage adapter."""
        client, _f, _kb, factory, _h, project_id = app_client
        profile_id = _seed_profile_with_file(factory, tmp_path, "--rules", b"x")

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}/files/%2E%2E",
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "PATH_TRAVERSAL"

    async def test_download_backslash_arg_name_returns_400_path_traversal(
        self, app_client, tmp_path: Path
    ) -> None:
        """GET with a backslash in the arg name is rejected as PATH_TRAVERSAL."""
        client, _f, _kb, factory, _h, project_id = app_client
        profile_id = _seed_profile_with_file(factory, tmp_path, "--rules", b"x")

        resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}/files/a%5Cb"
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "PATH_TRAVERSAL"
