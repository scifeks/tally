"""Integration tests for saved-scans write routes (POST and PUT)."""

from __future__ import annotations

import pytest

from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _seed_repo(factory, name: str) -> int:
    """Insert a row into ``repositories`` and return its id."""
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            (name,),
        )
        return int(cur.lastrowid)


class TestSavedScansCreate:
    """Tests for POST /api/v1/projects/{project_id}/saved-scans."""

    async def test_create_minimal_returns_201_hydrated_detail(self, app_client) -> None:
        """POST with minimal body returns 201 and the hydrated detail shape."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "weekly",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert isinstance(data["id"], int)
        assert data["name"] == "weekly"
        assert data["skipEnrichment"] is False
        assert data["repos"] == []
        assert data["tools"] == [{"toolName": "gitleaks"}]
        assert data["argProfiles"] == []

    async def test_create_accepts_snake_case_alias(self, app_client) -> None:
        """POST accepts snake_case body fields (D-1-14 alias channel)."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "snakey",
            "skip_enrichment": True,
            "repo_ids": [],
            "tool_names": ["gitleaks"],
            "arg_profile_ids": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["skipEnrichment"] is True
        assert data["tools"] == [{"toolName": "gitleaks"}]

    async def test_create_with_repos_and_arg_profile_hydrates_joins(
        self, app_client
    ) -> None:
        """POST with non-empty joins returns them hydrated in the response."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo_id = _seed_repo(factory, "auth-service")
        profiles_repo = ToolArgProfilesRepository(factory)
        profile_id = profiles_repo.insert(tool_name="gitleaks", name="verbose", args=[])

        body = {
            "name": "combo",
            "skipEnrichment": False,
            "repoIds": [repo_id],
            "toolNames": ["gitleaks"],
            "argProfileIds": [profile_id],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["repos"] == [
            {"id": repo_id, "name": "auth-service", "deletedAt": None}
        ]
        assert data["argProfiles"] == [
            {"id": profile_id, "toolName": "gitleaks", "name": "verbose"}
        ]

    async def test_create_validation_error_on_empty_name(self, app_client) -> None:
        """POST with empty name returns 422 with name field error."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        # Pydantic's min_length=1 rejects this at the schema layer; the field
        # path is reported under "fields[].field".
        fields = data["error"]["details"]["fields"]
        assert any("name" in entry["field"] for entry in fields)

    async def test_create_validation_error_when_tool_names_and_profiles_empty(
        self, app_client
    ) -> None:
        """POST with both tool/profile lists empty returns 422."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "empty",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": [],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        fields = data["error"]["details"]["fields"]
        assert any(
            entry["field"] == "toolNames"
            and "at least one of toolNames or argProfileIds" in entry["issue"]
            for entry in fields
        )

    async def test_create_validation_error_on_unknown_tool_name(
        self, app_client
    ) -> None:
        """POST with unknown tool name returns 422 with indexed field path."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "bogus-tool",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["nonexistent-tool"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        fields = data["error"]["details"]["fields"]
        assert any(entry["field"] == "toolNames[0]" for entry in fields)

    async def test_create_validation_error_on_unknown_arg_profile_id(
        self, app_client
    ) -> None:
        """POST with unknown arg profile id returns 422 with indexed field."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "bogus-profile",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [999],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        data = resp.json()
        fields = data["error"]["details"]["fields"]
        assert any(entry["field"] == "argProfileIds[0]" for entry in fields)

    async def test_create_409_on_duplicate_name(self, app_client) -> None:
        """POST with a name that already exists returns 409 CONFLICT."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "dupe",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        first = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert first.status_code == 201

        second = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"

    async def test_create_403_without_csrf(self, app_client) -> None:
        """POST without CSRF token returns 403."""
        client, _finding_id, _kb_mock, _factory, _mut_headers, project_id = app_client
        body = {
            "name": "no-csrf",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
        )
        assert resp.status_code == 403

    async def test_create_404_on_unknown_project(self, app_client) -> None:
        """POST on unknown project returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, _project_id = app_client
        body = {
            "name": "ghost",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.post(
            "/api/v1/projects/999999/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestSavedScansReplace:
    """Tests for PUT /api/v1/projects/{project_id}/saved-scans/{id}."""

    async def test_replace_minimal_returns_200_hydrated_detail(
        self, app_client
    ) -> None:
        """PUT replaces fields and returns the hydrated detail."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="initial",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        body = {
            "name": "updated",
            "skipEnrichment": True,
            "repoIds": [],
            "toolNames": ["semgrep"],
            "argProfileIds": [],
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == scan_id
        assert data["name"] == "updated"
        assert data["skipEnrichment"] is True
        assert data["tools"] == [{"toolName": "semgrep"}]

    async def test_replace_404_on_unknown_saved_scan(self, app_client) -> None:
        """PUT on unknown saved scan returns 404."""
        client, _finding_id, _kb_mock, _factory, mut_headers, project_id = app_client
        body = {
            "name": "missing",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/saved-scans/999999",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_replace_422_on_validation_error(self, app_client) -> None:
        """PUT with empty tool list and no profiles returns 422."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="seeded",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        body = {
            "name": "still-here",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": [],
            "argProfileIds": [],
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_replace_409_on_name_collision(self, app_client) -> None:
        """PUT with a name owned by another row returns 409."""
        client, _finding_id, _kb_mock, factory, mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        repo.insert(
            name="alpha",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        beta_id = repo.insert(
            name="beta",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        body = {
            "name": "alpha",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/saved-scans/{beta_id}",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    async def test_replace_403_without_csrf(self, app_client) -> None:
        """PUT without CSRF token returns 403."""
        client, _finding_id, _kb_mock, factory, _mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="no-csrf",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )
        body = {
            "name": "no-csrf",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
            json=body,
        )
        assert resp.status_code == 403


class TestSkipToolIdsAndSegmentsWireFields:
    """POST and PUT round-trip the new skipToolIds and segments fields."""

    async def test_create_with_skip_tool_ids_and_segments_echoed_in_response(
        self, app_client
    ) -> None:
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        body = {
            "name": "with-new-fields",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "skipToolIds": ["semgrep"],
            "segments": ["sast", "secrets"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["skipToolIds"] == ["semgrep"]
        assert set(data["segments"]) == {"sast", "secrets"}

    async def test_create_without_new_fields_defaults_to_empty(
        self, app_client
    ) -> None:
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        body = {
            "name": "no-new-fields",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["skipToolIds"] == []
        assert data["segments"] == []

    async def test_replace_updates_skip_tool_ids_and_segments(self, app_client) -> None:
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        repo = SavedScansRepository(factory)
        scan_id = repo.insert(
            name="initial",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["semgrep"],
            segments=["sast"],
            arg_profile_ids=[],
        )
        body = {
            "name": "initial",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "skipToolIds": ["semgrep"],
            "segments": ["secrets", "sca"],
            "argProfileIds": [],
        }
        resp = await client.put(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["skipToolIds"] == ["semgrep"]
        assert set(data["segments"]) == {"secrets", "sca"}

    async def test_validation_error_on_unknown_skip_tool_id(self, app_client) -> None:
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        body = {
            "name": "bad-skip-tool",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "skipToolIds": ["not-a-real-tool"],
            "segments": [],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422, resp.text
        errors = resp.json()["error"]["details"]["fields"]
        assert any("skipToolNames" in e["field"] for e in errors)

    async def test_validation_error_on_unknown_segment(self, app_client) -> None:
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        body = {
            "name": "bad-segment",
            "skipEnrichment": False,
            "repoIds": [],
            "toolNames": ["gitleaks"],
            "skipToolIds": [],
            "segments": ["badvalue"],
            "argProfileIds": [],
        }
        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans",
            json=body,
            headers=mut_headers,
        )
        assert resp.status_code == 422, resp.text
        errors = resp.json()["error"]["details"]["fields"]
        assert any("segments" in e["field"] for e in errors)
