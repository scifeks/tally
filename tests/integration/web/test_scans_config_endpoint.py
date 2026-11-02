"""Integration tests for GET /api/v1/projects/{id}/scans/config endpoint."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestScansConfigEndpoint:
    """Tests for GET /api/v1/projects/{project_id}/scans/config."""

    async def test_scans_config_lists_scanners(self, app_client) -> None:
        """GET /api/v1/projects/{id}/scans/config includes available_scanner_skills."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client

        resp = await client.get(f"/api/v1/projects/{project_id}/scans/config")
        assert resp.status_code == 200
        body = resp.json()
        assert "available_scanner_skills" in body
        slugs = {s["slug"] for s in body["available_scanner_skills"]}
        assert "scan-xss-stored" in slugs
        assert "scan-injection-sql" in slugs
