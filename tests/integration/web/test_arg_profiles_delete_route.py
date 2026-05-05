"""Integration tests for DELETE arg-profiles route."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.tool_arg_profiles.entry import ToolArgProfileFileArg
from infrastructure.storage.arg_files import ArgFilesStorageAdapter
from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


class TestArgProfilesDelete:
    """Tests for DELETE /api/v1/projects/{project_id}/arg-profiles/{id}."""

    async def test_delete_removes_row_returns_204(
        self, app_client, tmp_path: Path
    ) -> None:
        """DELETE removes profile and file directory, returns 204."""
        (
            client,
            _finding_id,
            _kb_mock,
            factory,
            mut_headers,
            project_id,
        ) = app_client

        # Seed an arg profile with a file arg
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="verbose", args=[])

        # Create and write file arg data to disk
        arg_files_dir = tmp_path / "projects" / "testproject" / "arg_files"
        arg_files_dir.mkdir(parents=True, exist_ok=True)
        storage = ArgFilesStorageAdapter(arg_files_dir)
        path = storage.write(profile_id, "--rules", b"test-rules-content")

        # Update profile with file arg
        file_arg = ToolArgProfileFileArg(name="--rules", path=path)
        repo.update(
            profile_id,
            tool_name="gitleaks",
            name="verbose",
            args=[file_arg],
        )

        # Verify file exists
        assert (arg_files_dir / str(profile_id)).exists()

        # DELETE the profile
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            headers=mut_headers,
        )
        assert resp.status_code == 204

        # Verify row is deleted
        list_resp = await client.get(f"/api/v1/projects/{project_id}/arg-profiles")
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["total"] == 0

        # Verify directory is deleted
        assert not (arg_files_dir / str(profile_id)).exists()

    async def test_delete_unknown_profile_returns_404(self, app_client) -> None:
        """DELETE unknown profile returns 404 NOT_FOUND."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/arg-profiles/999",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_delete_unknown_project_returns_404(self, app_client) -> None:
        """DELETE on unknown project returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, _project_id = app_client
        resp = await client.delete(
            "/api/v1/projects/999999/arg-profiles/1",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_delete_without_csrf_returns_403(self, app_client) -> None:
        """DELETE without CSRF token returns 403."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(tool_name="gitleaks", name="verbose", args=[])

        resp = await client.delete(f"/api/v1/projects/{project_id}/arg-profiles/1")
        assert resp.status_code == 403

    async def test_delete_referenced_by_saved_scan_returns_409_in_use(
        self, app_client
    ) -> None:
        """DELETE profile referenced by saved_scan returns 409 IN_USE."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="verbose", args=[])

        # Seed a saved_scan that references the profile
        saved_scans_repo = SavedScansRepository(factory)
        saved_scan_id = saved_scans_repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )

        # DELETE should return 409
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            headers=mut_headers,
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"]["code"] == "IN_USE"
        assert data["error"]["details"]["savedScanIds"] == [saved_scan_id]
        assert data["error"]["details"]["savedScanNames"] == ["weekly"]

        # Verify profile still exists
        detail_resp = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}"
        )
        assert detail_resp.status_code == 200

    async def test_delete_referenced_by_two_saved_scans_lists_both(
        self, app_client
    ) -> None:
        """DELETE lists all referencing saved_scans ordered by id."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="verbose", args=[])

        # Seed two saved_scans that reference the profile
        saved_scans_repo = SavedScansRepository(factory)
        scan_id_1 = saved_scans_repo.insert(
            name="daily",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )
        scan_id_2 = saved_scans_repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[profile_id],
        )

        # DELETE should return 409 with both references
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            headers=mut_headers,
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"]["code"] == "IN_USE"

        # Both IDs and names should be in response, ordered by ID
        expected_ids = sorted([scan_id_1, scan_id_2])
        assert data["error"]["details"]["savedScanIds"] == expected_ids
        # Names should match the order
        assert len(data["error"]["details"]["savedScanNames"]) == 2
