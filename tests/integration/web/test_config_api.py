"""Tests for GET /api/config — field configuration endpoint."""

from __future__ import annotations

import pytest

from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
    STATUS_LEVELS,
)
from tests.integration.web.conftest import AUTH

pytestmark = pytest.mark.integration


class TestGetConfig:
    async def test_returns_editable_fields(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert "editable_fields" in data

    async def test_requires_auth(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/")
        assert response.status_code == 401

    async def test_severity_options_match_constants(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/", headers=AUTH)
        fields = response.json()["editable_fields"]
        assert set(fields["severity"]["options"]) == SEVERITY_LEVELS

    async def test_confidence_options_match_constants(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/", headers=AUTH)
        fields = response.json()["editable_fields"]
        assert set(fields["confidence"]["options"]) == CONFIDENCE_LEVELS

    async def test_status_options_match_constants(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/", headers=AUTH)
        fields = response.json()["editable_fields"]
        assert set(fields["status"]["options"]) == STATUS_LEVELS

    async def test_finding_type_options_match_constants(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/", headers=AUTH)
        fields = response.json()["editable_fields"]
        assert set(fields["finding_type"]["options"]) == FINDING_TYPES

    async def test_each_field_has_editor_key(self, app_client) -> None:
        client, _, _, _ = app_client
        response = await client.get("/api/config/", headers=AUTH)
        fields = response.json()["editable_fields"]
        for key, spec in fields.items():
            assert "editor" in spec, f"field '{key}' is missing 'editor'"
            assert spec["editor"] in ("select", "text", "boolean", "tags"), (
                f"field '{key}' has unknown editor '{spec['editor']}'"
            )
