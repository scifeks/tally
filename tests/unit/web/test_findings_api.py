"""Tests for GET and PATCH /api/findings endpoints."""

from __future__ import annotations

import pytest

from tests.unit.web.conftest import AUTH

pytestmark = pytest.mark.integration


class TestGetFindings:
    async def test_type_flags_stripped_from_meta(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/findings/", headers=AUTH)
        assert response.status_code == 200
        findings = response.json()
        assert len(findings) >= 1
        meta = findings[0]["meta"]
        assert not any(k.startswith("type_") for k in meta)
        assert "profile" in meta

    async def test_get_by_id_returns_404_for_unknown(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/findings/99999", headers=AUTH)
        assert response.status_code == 404

    async def test_get_by_id_returns_correct_finding(self, app_client) -> None:
        client, finding_id, _, _ = app_client
        response = await client.get(f"/api/findings/{finding_id}", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == finding_id
        assert data["tool"] == "semgrep"
        assert data["severity"] == "high"
        assert data["domain"] == "code"

    async def test_missing_auth_header_returns_401(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/findings/")
        assert response.status_code == 401

    async def test_wrong_token_returns_401(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get(
            "/api/findings/",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401


class TestPatchFinding:
    async def test_patch_updates_editable_field(self, app_client) -> None:
        client, finding_id, _, factory = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "critical"},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["severity"] == "critical"
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT severity FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        assert row["severity"] == "critical"

    async def test_patch_sets_triaged_by_analyst_web(self, app_client) -> None:
        client, finding_id, _, factory = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"status": "false_positive"},
            headers=AUTH,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        assert row["triaged_by"] == "analyst_web"
        assert row["triaged_at"] is not None

    async def test_chroma_sync_is_attempted(self, app_client) -> None:
        client, finding_id, rag_mock, _ = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "low"},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert rag_mock.update_metadata.called

    async def test_chroma_sync_failure_returns_200(self, app_client) -> None:
        client, finding_id, rag_mock, _ = app_client
        rag_mock.update_metadata.side_effect = Exception("chroma error")
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "low"},
            headers=AUTH,
        )
        assert response.status_code == 200

    async def test_patch_invalid_severity_returns_422(self, app_client) -> None:
        client, finding_id, _, _ = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "extreme"},
            headers=AUTH,
        )
        assert response.status_code == 422

    async def test_patch_invalid_status_returns_422(self, app_client) -> None:
        client, finding_id, _, _ = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"status": "maybe"},
            headers=AUTH,
        )
        assert response.status_code == 422
