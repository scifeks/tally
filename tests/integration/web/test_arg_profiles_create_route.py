"""Integration tests for POST arg-profiles multipart create route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _payload(tool_name: str, name: str, args: list[dict]) -> str:
    """Serialize a payload object to JSON."""
    return json.dumps({"toolName": tool_name, "name": name, "args": args})


class TestArgProfilesCreate:
    """Tests for POST /api/v1/projects/{project_id}/arg-profiles."""

    async def test_create_no_file_args_returns_201_with_payload(
        self, app_client
    ) -> None:
        """POST with flag and string args returns 201 and persists row."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client

        files = {
            "payload": (
                None,
                _payload(
                    "gitleaks",
                    "verbose",
                    [
                        {"name": "--verbose", "type": "flag"},
                        {"name": "--config", "type": "string", "value": "/etc/x"},
                    ],
                ),
            ),
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files=files,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["toolName"] == "gitleaks"
        assert body["name"] == "verbose"
        assert len(body["args"]) == 2
        assert body["args"][0] == {"name": "--verbose", "type": "flag"}
        assert body["args"][1] == {
            "name": "--config",
            "type": "string",
            "value": "/etc/x",
            "operator": "",
        }
        profile_id = body["id"]

        detail = await client.get(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}"
        )
        assert detail.status_code == 200
        assert detail.json()["name"] == "verbose"

    async def test_create_with_one_file_arg_writes_bytes_to_disk(
        self, app_client, tmp_path: Path
    ) -> None:
        """POST with a file arg writes the bytes under arg_files/<profile_id>."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client

        files = {
            "payload": (
                None,
                _payload(
                    "gitleaks",
                    "with-rules",
                    [{"name": "--rules", "type": "file"}],
                ),
            ),
            "--rules": ("rules.yml", b"rule-bytes", "application/octet-stream"),
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files=files,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        profile_id = body["id"]

        arg_files_dir = tmp_path / "projects" / "testproject" / "arg_files"
        on_disk = arg_files_dir / str(profile_id) / "--rules" / "rules.yml"
        assert on_disk.is_file()
        assert on_disk.read_bytes() == b"rule-bytes"

        assert body["args"][0]["type"] == "file"
        assert body["args"][0]["name"] == "--rules"
        assert body["args"][0]["originalFilename"] == "rules.yml"
        assert body["args"][0]["downloadUrl"].endswith(
            f"/arg-profiles/{profile_id}/files/--rules"
        )

    async def test_create_with_mixed_args_persists_two_files(
        self, app_client, tmp_path: Path
    ) -> None:
        """POST with two file args plus flag and string persists both files."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client

        files = {
            "payload": (
                None,
                _payload(
                    "gitleaks",
                    "mixed",
                    [
                        {"name": "--verbose", "type": "flag"},
                        {"name": "--rules", "type": "file"},
                        {"name": "--mode", "type": "string", "value": "deep"},
                        {"name": "--allowlist", "type": "file"},
                    ],
                ),
            ),
            "--rules": ("a", b"AAA", "application/octet-stream"),
            "--allowlist": ("b", b"BBB", "application/octet-stream"),
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files=files,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        profile_id = body["id"]
        assert len(body["args"]) == 4

        arg_files_dir = tmp_path / "projects" / "testproject" / "arg_files"
        assert (
            arg_files_dir / str(profile_id) / "--rules" / "a"
        ).read_bytes() == b"AAA"
        assert (
            arg_files_dir / str(profile_id) / "--allowlist" / "b"
        ).read_bytes() == b"BBB"

    async def test_create_unique_conflict_returns_409(self, app_client) -> None:
        """POST duplicating (toolName, name) returns 409 CONFLICT."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(tool_name="gitleaks", name="dup", args=[])

        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={
                "payload": (None, _payload("gitleaks", "dup", [])),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    async def test_create_without_csrf_returns_403(self, app_client) -> None:
        """POST without CSRF header returns 403."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client
        resp = await client.post(
            f"/api/v1/projects/{project_id}/arg-profiles",
            files={"payload": (None, _payload("gitleaks", "x", []))},
        )
        assert resp.status_code == 403

    async def test_create_unknown_project_returns_404(self, app_client) -> None:
        """POST to unknown project returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, _project_id = app_client
        resp = await client.post(
            "/api/v1/projects/999999/arg-profiles",
            files={"payload": (None, _payload("gitleaks", "x", []))},
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
