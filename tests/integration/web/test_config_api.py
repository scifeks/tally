"""Tests for GET /api/v1/config/field-specs field configuration endpoint."""

from __future__ import annotations

import pytest

from domain.findings.severity import Severity
from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    DOMAINS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
    STATUS_LEVELS,
)

pytestmark = pytest.mark.integration


class TestGetConfig:
    async def test_returns_editable_fields(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        assert response.status_code == 200
        data = response.json()
        assert "editable_fields" in data

    async def test_severity_options_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        fields = response.json()["editable_fields"]
        assert set(fields["severity"]["options"]) == SEVERITY_LEVELS

    async def test_confidence_options_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        fields = response.json()["editable_fields"]
        assert set(fields["confidence"]["options"]) == CONFIDENCE_LEVELS

    async def test_status_options_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        fields = response.json()["editable_fields"]
        assert set(fields["status"]["options"]) == STATUS_LEVELS

    async def test_finding_type_options_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        fields = response.json()["editable_fields"]
        assert set(fields["finding_type"]["options"]) == FINDING_TYPES

    async def test_each_field_has_editor_key(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        fields = response.json()["editable_fields"]
        for key, spec in fields.items():
            assert "editor" in spec, f"field '{key}' is missing 'editor'"
            assert spec["editor"] in ("select", "text", "boolean", "tags"), (
                f"field '{key}' has unknown editor '{spec['editor']}'"
            )


class TestEnumsBlock:
    async def test_enums_key_present(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        assert "enums" in response.json()

    async def test_severities_match_domain_order(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        enums = response.json()["enums"]
        expected = [s.label for s in Severity.all_ordered()]
        assert enums["severities"] == expected

    async def test_domains_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        enums = response.json()["enums"]
        assert set(enums["domains"]) == DOMAINS

    async def test_confidence_levels_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        enums = response.json()["enums"]
        assert set(enums["confidence_levels"]) == CONFIDENCE_LEVELS

    async def test_statuses_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        enums = response.json()["enums"]
        assert set(enums["statuses"]) == STATUS_LEVELS

    async def test_finding_types_match_constants(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/config/field-specs")
        enums = response.json()["enums"]
        assert set(enums["finding_types"]) == FINDING_TYPES
