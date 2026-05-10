"""Integration tests for GET /api/v1/projects/:id/locks."""

from __future__ import annotations

import pytest

from application.locking import get_registry

pytestmark = pytest.mark.integration


class TestGetProjectLocks:
    async def test_returns_empty_locks_by_default(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client

        response = await client.get(f"/api/v1/projects/{project_id}/locks")

        assert response.status_code == 200
        data = response.json()
        assert data["project_id"] == project_id
        assert data["finding_locks"] == []
        assert data["job_locks"] == {
            "scan": None,
            "triage": None,
            "report": None,
        }

    async def test_returns_held_finding_locks(self, app_client) -> None:
        client, finding_id, _, _, _, project_id = app_client
        registry = get_registry()
        registry.acquire_findings([finding_id], "triage-run:42")

        response = await client.get(f"/api/v1/projects/{project_id}/locks")

        assert response.status_code == 200
        data = response.json()
        finding_locks = data["finding_locks"]
        assert any(
            fl["id"] == finding_id and fl["holder"] == "triage-run:42"
            for fl in finding_locks
        )

    async def test_returns_held_job_locks(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        registry = get_registry()
        registry.acquire_job("triage", "triage-run:42")

        response = await client.get(f"/api/v1/projects/{project_id}/locks")

        assert response.status_code == 200
        data = response.json()
        assert data["job_locks"]["triage"] == "triage-run:42"
        assert data["job_locks"]["scan"] is None
        assert data["job_locks"]["report"] is None

    async def test_unknown_project_returns_404(self, app_client) -> None:
        client, _, _, _, _, _ = app_client

        response = await client.get("/api/v1/projects/9999/locks")

        assert response.status_code == 404

    async def test_requires_authentication(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        import httpx

        transport = client._transport
        async with httpx.AsyncClient(
            transport=transport,
            base_url=str(client.base_url),
        ) as unauthed_client:
            response = await unauthed_client.get(f"/api/v1/projects/{project_id}/locks")

        assert response.status_code == 401
