"""Integration tests for lock enforcement on finding mutation endpoints."""

from __future__ import annotations

import pytest

from application.locking import get_registry

pytestmark = pytest.mark.integration


class TestPatchFindingLocked:
    async def test_patch_unlocked_finding_returns_200(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client
        response = await client.patch(
            f"/api/v1/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200

    async def test_patch_locked_finding_returns_409(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client
        registry = get_registry()
        registry.acquire_findings([finding_id], "triage-run:999")

        response = await client.patch(
            f"/api/v1/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "FINDING_LOCKED"
        assert str(finding_id) in error["details"]["holders"]

    async def test_patch_locked_finding_error_envelope(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client
        registry = get_registry()
        registry.acquire_findings([finding_id], "triage-run:999")

        response = await client.patch(
            f"/api/v1/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )

        body = response.json()
        assert "error" in body
        assert body["error"]["details"]["conflicting_ids"] == [finding_id]


class TestGetFindingLockFields:
    async def test_get_locked_finding_shows_is_locked_true(self, app_client) -> None:
        client, finding_id, _, _, _ = app_client
        registry = get_registry()
        registry.acquire_findings([finding_id], "triage-run:999")

        response = await client.get(f"/api/v1/findings/{finding_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["is_locked"] is True
        assert data["lock_holder"] == "triage-run:999"

    async def test_get_unlocked_finding_shows_is_locked_false(self, app_client) -> None:
        client, finding_id, _, _, _ = app_client

        response = await client.get(f"/api/v1/findings/{finding_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["is_locked"] is False
        assert data["lock_holder"] is None


class TestBatchPatchPartition:
    async def test_batch_returns_three_bucket_partition(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client
        registry = get_registry()
        registry.acquire_findings([finding_id], "triage-run:999")

        bogus_id = 99999

        response = await client.patch(
            "/api/v1/findings/batch",
            json={"ids": [finding_id, bogus_id], "severity": "low"},
            headers=mut_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert finding_id not in data["updated"]
        assert finding_id in data["skipped_locked"]
        assert bogus_id in data["not_found"]
        assert data["skip_reasons"][str(finding_id)] == "FINDING_LOCKED"

    async def test_batch_all_unlocked_all_updated(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client

        response = await client.patch(
            "/api/v1/findings/batch",
            json={"ids": [finding_id], "severity": "low"},
            headers=mut_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert finding_id in data["updated"]
        assert data["skipped_locked"] == []
        assert data["not_found"] == []
