"""Write safety tests for PATCH /api/v1/projects/{project_id}/findings/{id}.

Verifies that locked fields cannot be overwritten via the PATCH endpoint,
and that the meta blob is merged (not replaced) while preserving type_*
flags on every write.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration


class TestLockedFields:
    async def test_url_not_updated_on_patch(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"url": "https://attacker.com"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT url FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        assert row["url"] == "https://original.com/path"

    async def test_tool_not_updated_on_patch(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"tool": "gitleaks"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT tool FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        assert row["tool"] == "semgrep"

    async def test_fingerprint_not_updated_on_patch(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        original_fp = row["fingerprint"]
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"fingerprint": "tampered"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        assert row["fingerprint"] == original_fp


class TestMetaPreservation:
    async def test_type_flags_preserved_on_meta_update(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"meta_remediation": "new remediation"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT meta FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        meta = json.loads(row["meta"])
        assert meta["type_secret"] is True
        assert meta["type_vulnerability"] is False
        assert meta["remediation"] == "new remediation"
        assert "profile" in meta

    async def test_meta_update_merges_not_replaces(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"meta_risk_type": "injection"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT meta FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        meta = json.loads(row["meta"])
        assert meta["risk_type"] == "injection"
        assert meta["remediation"] == "old"
        assert meta["author"] == "jdoe"
        assert meta["commit"] == "abc123"
        assert meta["type_secret"] is True

    async def test_patch_unknown_id_returns_404(self, app_client) -> None:
        client, _, _, _, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/99999",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 404
