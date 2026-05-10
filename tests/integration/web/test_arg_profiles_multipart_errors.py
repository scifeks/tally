"""Integration tests for arg-profile multipart error envelopes."""

from __future__ import annotations

import json

import pytest

from domain.tool_arg_profiles.entry import ToolArgProfileFileArg
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _payload(tool_name: str, name: str, args: list[dict]) -> str:
    """Serialize a payload object to JSON."""
    return json.dumps({"toolName": tool_name, "name": name, "args": args})


class TestArgProfilesMultipartErrors:
    """Error-envelope tests covering both POST and PUT multipart routes."""

    async def test_post_missing_payload_field_returns_422(self, app_client) -> None:
        """POST with no `payload` form field returns 422 VALIDATION_ERROR."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={
                "--rules": ("a", b"x", "application/octet-stream"),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_post_invalid_json_in_payload_returns_422(self, app_client) -> None:
        """POST with malformed JSON in payload returns 422 VALIDATION_ERROR."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={"payload": (None, "not-json")},
            headers=mut_headers,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_post_payload_missing_tool_name_returns_422(self, app_client) -> None:
        """POST with payload missing toolName returns 422 VALIDATION_ERROR."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={"payload": (None, json.dumps({"name": "x", "args": []}))},
            headers=mut_headers,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_post_file_arg_without_upload_field_returns_422_with_arg_name(
        self, app_client
    ) -> None:
        """File arg in payload without matching UploadFile reports arg name."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={
                "payload": (
                    None,
                    _payload(
                        "gitleaks",
                        "missing",
                        [{"name": "--rules", "type": "file"}],
                    ),
                ),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["details"]["fields"] == [
            {"field": "--rules", "issue": "missing upload field"}
        ]

    async def test_post_arg_name_with_slash_returns_400_path_traversal(
        self, app_client
    ) -> None:
        """File arg name with `/` returns 400 PATH_TRAVERSAL."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={
                "payload": (
                    None,
                    _payload(
                        "gitleaks",
                        "bad",
                        [{"name": "subdir/--rules", "type": "file"}],
                    ),
                ),
                "subdir/--rules": ("x", b"x", "application/octet-stream"),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "PATH_TRAVERSAL"

    async def test_post_arg_name_dotdot_returns_400_path_traversal(
        self, app_client
    ) -> None:
        """File arg name `..` returns 400 PATH_TRAVERSAL."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={
                "payload": (
                    None,
                    _payload(
                        "gitleaks",
                        "bad",
                        [{"name": "..", "type": "file"}],
                    ),
                ),
                "..": ("x", b"x", "application/octet-stream"),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "PATH_TRAVERSAL"

    async def test_put_keep_existing_with_no_stored_bytes_returns_422(
        self, app_client
    ) -> None:
        """PUT keep-existing for an arg name with no stored bytes returns 422."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        # Seed a profile with a file arg row but never write bytes to disk.
        profile_id = repo.insert(
            tool_name="gitleaks",
            name="phantom",
            args=[
                ToolArgProfileFileArg(
                    name="--rules",
                    path="arg_files/0/--rules",
                ),
            ],
        )
        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            files={
                "payload": (
                    None,
                    _payload(
                        "gitleaks",
                        "phantom",
                        [{"name": "--rules", "type": "file"}],
                    ),
                ),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        fields = body["error"]["details"]["fields"]
        assert any("keep-existing" in f["issue"] for f in fields), (
            f"unexpected envelope: {body}"
        )
