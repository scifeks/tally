"""Integration tests for GET /platform/v1/capabilities endpoint."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestCapabilitiesEndpoint:
    """Tests for GET /platform/v1/capabilities."""

    async def test_capabilities_includes_background_mode(self, app_client) -> None:
        """GET /api/v1/capabilities includes background_mode field."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, _project_id = app_client

        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert "background_mode" in body
        bm = body["background_mode"]
        assert set(bm) >= {
            "oauth_available",
            "api_key_available",
            "interactive_available",
        }

    async def test_capabilities_default_billing_method_optional(
        self, app_client
    ) -> None:
        """GET /api/v1/capabilities includes default_billing_method."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, _project_id = app_client

        resp = await client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert "default_billing_method" in body
