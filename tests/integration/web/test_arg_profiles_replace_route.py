"""Integration tests for PUT arg-profiles multipart replace route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.tool_arg_profiles.entry import ToolArgProfileFileArg
from infrastructure.storage.arg_files import ArgFilesStorageAdapter
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _payload(tool_name: str, name: str, args: list[dict]) -> str:
    """Serialize a payload object to JSON."""
    return json.dumps({"toolName": tool_name, "name": name, "args": args})


def _arg_files_dir(tmp_path: Path) -> Path:
    """Return the on-disk arg_files directory for the testproject fixture."""
    return tmp_path / "projects" / "testproject" / "arg_files"


class TestArgProfilesReplace:
    """Tests for PUT /api/v1/projects/{project_id}/arg-profiles/{id}."""

    async def test_replace_metadata_only_returns_200(self, app_client) -> None:
        """PUT renaming a no-files profile returns 200 and updates row."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="orig", args=[])

        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            files={
                "payload": (
                    None,
                    _payload(
                        "trufflehog",
                        "renamed",
                        [{"name": "--verbose", "type": "flag"}],
                    ),
                ),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == profile_id
        assert body["toolName"] == "trufflehog"
        assert body["name"] == "renamed"
        assert len(body["args"]) == 1

    async def test_replace_adds_new_file_arg_writes_bytes(
        self, app_client, tmp_path: Path
    ) -> None:
        """PUT adding a file arg to a no-files profile persists the bytes."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="add-file", args=[])

        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            files={
                "payload": (
                    None,
                    _payload(
                        "gitleaks",
                        "add-file",
                        [{"name": "--rules", "type": "file"}],
                    ),
                ),
                "--rules": ("rules.yml", b"new-bytes", "application/octet-stream"),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 200, resp.text

        on_disk = _arg_files_dir(tmp_path) / str(profile_id) / "--rules" / "rules.yml"
        assert on_disk.read_bytes() == b"new-bytes"

    async def test_replace_keep_existing_preserves_bytes(
        self, app_client, tmp_path: Path
    ) -> None:
        """PUT with no upload for a file arg keeps the original bytes."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="keep", args=[])

        storage = ArgFilesStorageAdapter(_arg_files_dir(tmp_path))
        path = storage.write(profile_id, "--rules", b"original-bytes")
        repo.update(
            profile_id,
            tool_name="gitleaks",
            name="keep",
            args=[ToolArgProfileFileArg(name="--rules", path=path)],
        )

        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            files={
                "payload": (
                    None,
                    _payload(
                        "gitleaks",
                        "keep",
                        [{"name": "--rules", "type": "file"}],
                    ),
                ),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 200, resp.text

        on_disk = _arg_files_dir(tmp_path) / str(profile_id) / "--rules" / "--rules"
        assert on_disk.read_bytes() == b"original-bytes"
        body = resp.json()
        assert body["args"][0]["path"] == path

    async def test_replace_drops_orphan_file_arg_deletes_bytes(
        self, app_client, tmp_path: Path
    ) -> None:
        """PUT removing a file arg from the list deletes its file."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="orphan", args=[])

        storage = ArgFilesStorageAdapter(_arg_files_dir(tmp_path))
        path = storage.write(profile_id, "--rules", b"to-be-orphaned")
        repo.update(
            profile_id,
            tool_name="gitleaks",
            name="orphan",
            args=[ToolArgProfileFileArg(name="--rules", path=path)],
        )

        on_disk = _arg_files_dir(tmp_path) / str(profile_id) / "--rules"
        assert on_disk.exists()

        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            files={
                "payload": (None, _payload("gitleaks", "orphan", [])),
            },
            headers=mut_headers,
        )
        assert resp.status_code == 200, resp.text
        assert not on_disk.exists()

    async def test_replace_unknown_profile_returns_404(self, app_client) -> None:
        """PUT on a nonexistent profile id returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/9999",
            files={"payload": (None, _payload("gitleaks", "x", []))},
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_replace_unknown_project_returns_404(self, app_client) -> None:
        """PUT under an unknown project returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, _project_id = app_client
        resp = await client.put(
            "/api/v1/projects/999999/arg-profiles/1",
            files={"payload": (None, _payload("gitleaks", "x", []))},
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_replace_without_csrf_returns_403(self, app_client) -> None:
        """PUT without CSRF token returns 403."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        profile_id = repo.insert(tool_name="gitleaks", name="x", args=[])
        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{profile_id}",
            files={"payload": (None, _payload("gitleaks", "x", []))},
        )
        assert resp.status_code == 403

    async def test_replace_unique_conflict_on_rename_returns_409(
        self, app_client
    ) -> None:
        """PUT renaming to an existing (toolName, name) returns 409 CONFLICT."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = ToolArgProfilesRepository(factory)
        repo.insert(tool_name="gitleaks", name="taken", args=[])
        other_id = repo.insert(tool_name="gitleaks", name="other", args=[])

        resp = await client.put(
            f"/api/v1/projects/{project_id}/arg-profiles/{other_id}",
            files={"payload": (None, _payload("gitleaks", "taken", []))},
            headers=mut_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"
