"""Integration tests for saved-scans DELETE route."""

from __future__ import annotations

import pytest

from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _seed_repo(factory, name: str) -> int:
    """Insert a row into ``repositories`` and return its id."""
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            (name,),
        )
        return int(cur.lastrowid)


class TestSavedScansDelete:
    """Tests for DELETE /api/v1/projects/{project_id}/saved-scans/{id}."""

    async def test_delete_removes_row_returns_204(self, app_client) -> None:
        """DELETE removes the saved scan and returns 204."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="ephemeral",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        resp = await client.delete(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
            headers=mut_headers,
        )
        assert resp.status_code == 204

        list_resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans")
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 0

    async def test_delete_cascades_join_rows(self, app_client) -> None:
        """DELETE clears saved_scan_repos / _tools / _arg_profiles for that id."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo_id = _seed_repo(factory, "auth-service")
        profiles_repo = ToolArgProfilesRepository(factory)
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])

        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="cascade",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            arg_profile_ids=[profile_id],
        )

        with factory.connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM saved_scan_repos WHERE saved_scan_id = ?",
                    (scan_id,),
                ).fetchone()[0]
                == 1
            )

        resp = await client.delete(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
            headers=mut_headers,
        )
        assert resp.status_code == 204

        with factory.connect() as conn:
            for table in (
                "saved_scan_repos",
                "saved_scan_tools",
                "saved_scan_arg_profiles",
            ):
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE saved_scan_id = ?",
                    (scan_id,),
                ).fetchone()[0]
                assert count == 0, f"{table} still has rows for scan {scan_id}"

    async def test_delete_unknown_saved_scan_returns_404(self, app_client) -> None:
        """DELETE on unknown saved scan returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/saved-scans/999999",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_delete_unknown_project_returns_404(self, app_client) -> None:
        """DELETE on unknown project returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, _project_id = app_client
        resp = await client.delete(
            "/api/v1/projects/999999/saved-scans/1",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_delete_403_without_csrf(self, app_client) -> None:
        """DELETE without CSRF token returns 403."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="no-csrf",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
        )
        assert resp.status_code == 403
