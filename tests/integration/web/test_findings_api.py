"""Tests for GET and PATCH /api/findings endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestAuthMiddlewareScope:
    async def test_non_api_path_does_not_require_session(self, app_client) -> None:
        """Browser must load the SPA without session cookies.

        Middleware must only enforce session auth on /api/* routes. A GET
        to the SPA root must not return 401 — the browser needs index.html
        to load before it can complete the handshake exchange.
        """
        client, _, _, _, _ = app_client
        response = await client.get("/")
        assert response.status_code != 401


class TestGetFindings:
    async def test_type_flags_stripped_from_meta(self, app_client) -> None:
        client, _, _, _, _ = app_client
        response = await client.get("/api/findings/")
        assert response.status_code == 200
        findings = response.json()
        assert len(findings) >= 1
        meta = findings[0]["meta"]
        assert not any(k.startswith("type_") for k in meta)
        assert "profile" in meta

    async def test_get_by_id_returns_404_for_unknown(self, app_client) -> None:
        client, _, _, _, _ = app_client
        response = await client.get("/api/findings/99999")
        assert response.status_code == 404

    async def test_get_by_id_returns_correct_finding(self, app_client) -> None:
        client, finding_id, _, _, _ = app_client
        response = await client.get(f"/api/findings/{finding_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == finding_id
        assert data["tool"] == "semgrep"
        assert data["severity"] == "high"
        assert data["domain"] == "code"


class TestPatchFinding:
    async def test_patch_updates_editable_field(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "critical"},
            headers=mut_headers,
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
        client, finding_id, _, factory, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"status": "false_positive"},
            headers=mut_headers,
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
        client, finding_id, rag_mock, _, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert rag_mock.add_documents.called

    async def test_chroma_sync_upserts_on_severity_change(self, app_client) -> None:
        client, finding_id, rag_mock, _, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert rag_mock.add_documents.called

    async def test_chroma_sync_upserts_on_should_report_change(
        self, app_client
    ) -> None:
        client, finding_id, rag_mock, _, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"should_report": True},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert rag_mock.add_documents.called

    async def test_chroma_sync_failure_returns_200(self, app_client) -> None:
        client, finding_id, rag_mock, _, mut_headers = app_client
        rag_mock.add_documents.side_effect = Exception("chroma error")
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200

    async def test_patch_invalid_severity_returns_422(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"severity": "extreme"},
            headers=mut_headers,
        )
        assert response.status_code == 422

    async def test_patch_invalid_status_returns_422(self, app_client) -> None:
        client, finding_id, _, _, mut_headers = app_client
        response = await client.patch(
            f"/api/findings/{finding_id}",
            json={"status": "maybe"},
            headers=mut_headers,
        )
        assert response.status_code == 422
