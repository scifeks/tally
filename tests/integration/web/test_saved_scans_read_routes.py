"""Integration tests for saved-scans read routes (GET list and detail)."""

from __future__ import annotations

import pytest

from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _seed_repo(factory, name: str, *, deleted_at: str | None = None) -> int:
    """Insert a row into ``repositories`` and return its id."""
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, deleted_at) VALUES (?, ?)",
            (name, deleted_at),
        )
        return int(cur.lastrowid)


class TestSavedScansList:
    """Tests for GET /api/v1/projects/{project_id}/saved-scans."""

    async def test_list_returns_empty_envelope_when_no_saved_scans(
        self, app_client
    ) -> None:
        """GET with no seeded saved scans returns empty list envelope."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client
        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    async def test_list_returns_seeded_scan_in_camel_case(self, app_client) -> None:
        """GET lists a seeded saved scan with camelCase fields."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        repo.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["name"] == "weekly"
        assert item["skipEnrichment"] is False
        assert item["repoIds"] == []
        assert item["toolNames"] == ["gitleaks"]
        assert item["argProfileIds"] == []
        assert "createdAt" in item
        assert "updatedAt" in item

    async def test_list_pagination_offset_limit_respected(self, app_client) -> None:
        """GET with offset and limit respects pagination."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        for nm in ("a", "b", "c"):
            repo.insert(
                name=nm,
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                arg_profile_ids=[],
            )

        resp = await client.get(
            f"/api/v1/projects/{project_id}/saved-scans?offset=1&limit=1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3
        assert data["offset"] == 1
        assert data["limit"] == 1

    async def test_list_unknown_project_returns_404(self, app_client) -> None:
        """GET on unknown project returns 404 NOT_FOUND."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, _project_id = app_client
        resp = await client.get("/api/v1/projects/999999/saved-scans")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_list_carries_join_arrays(self, app_client) -> None:
        """List items expose multi-value repoIds, toolNames, argProfileIds."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo_id_one = _seed_repo(factory, "auth-service")
        repo_id_two = _seed_repo(factory, "payments")
        profiles_repo = ToolArgProfilesRepository(factory)
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])

        repo = SavedScansRepository(factory)
        repo.insert(
            name="combo",
            skip_enrichment=True,
            repo_ids=[repo_id_one, repo_id_two],
            tool_names=["gitleaks", "semgrep"],
            arg_profile_ids=[profile_id],
        )

        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["skipEnrichment"] is True
        assert item["repoIds"] == [repo_id_one, repo_id_two]
        assert item["toolNames"] == ["gitleaks", "semgrep"]
        assert item["argProfileIds"] == [profile_id]


class TestSavedScansDetail:
    """Tests for GET /api/v1/projects/{project_id}/saved-scans/{id}."""

    async def test_detail_returns_hydrated_scan_in_camel_case(self, app_client) -> None:
        """GET detail returns hydrated saved scan with camelCase fields."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo_id = _seed_repo(factory, "auth-service")
        profiles_repo = ToolArgProfilesRepository(factory)
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="hydrated",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            arg_profile_ids=[profile_id],
        )

        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans/{scan_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == scan_id
        assert data["name"] == "hydrated"
        assert data["skipEnrichment"] is False
        assert data["repos"] == [
            {"id": repo_id, "name": "auth-service", "deletedAt": None}
        ]
        assert data["tools"] == [{"toolName": "gitleaks"}]
        assert data["argProfiles"] == [
            {"id": profile_id, "toolName": "gitleaks", "name": "verbose"}
        ]
        assert "createdAt" in data
        assert "updatedAt" in data

    async def test_detail_surfaces_soft_deleted_repo(self, app_client) -> None:
        """GET detail surfaces deletedAt for soft-deleted repos."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo_id = _seed_repo(factory, "old-service", deleted_at="2026-05-01T00:00:00Z")
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="legacy",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans/{scan_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["repos"]) == 1
        assert data["repos"][0]["deletedAt"] == "2026-05-01T00:00:00Z"

    async def test_detail_unknown_saved_scan_returns_404(self, app_client) -> None:
        """GET detail with unknown id returns 404."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client
        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans/999999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_detail_unknown_project_returns_404(self, app_client) -> None:
        """GET detail on unknown project returns 404."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, _project_id = app_client
        resp = await client.get("/api/v1/projects/999999/saved-scans/1")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_detail_skip_enrichment_true_serializes_camelcase(
        self, app_client
    ) -> None:
        """skipEnrichment=true round-trips through the detail response."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="skipped",
            skip_enrichment=True,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        resp = await client.get(f"/api/v1/projects/{project_id}/saved-scans/{scan_id}")
        assert resp.status_code == 200
        assert resp.json()["skipEnrichment"] is True
