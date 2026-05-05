"""Unit tests for saved-scan request and response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from web.api.saved_scans_schemas import (
    SavedScanArgProfileResponse,
    SavedScanDetailResponse,
    SavedScanListItemResponse,
    SavedScanListResponse,
    SavedScanRepoResponse,
    SavedScanToolResponse,
    SavedScanWriteRequest,
    StaleSavedScanArgProfileItemDetail,
    StaleSavedScanDetails,
    StaleSavedScanRepoItemDetail,
    StaleSavedScanToolItemDetail,
)


class TestSavedScansSchemas:
    def test_write_request_camel_and_snake_round_trip(self) -> None:
        camel = {
            "name": "Weekly secrets sweep",
            "skipEnrichment": False,
            "repoIds": [1, 2],
            "toolNames": ["gitleaks", "trufflehog"],
            "argProfileIds": [12, 14],
        }
        snake = {
            "name": "Weekly secrets sweep",
            "skip_enrichment": False,
            "repo_ids": [1, 2],
            "tool_names": ["gitleaks", "trufflehog"],
            "arg_profile_ids": [12, 14],
        }
        m_camel = SavedScanWriteRequest.model_validate(camel)
        m_snake = SavedScanWriteRequest.model_validate(snake)
        assert m_camel.name == "Weekly secrets sweep"
        assert m_camel.skip_enrichment is False
        assert m_camel.repo_ids == [1, 2]
        assert m_camel.tool_names == ["gitleaks", "trufflehog"]
        assert m_camel.arg_profile_ids == [12, 14]
        assert m_snake.repo_ids == [1, 2]

    def test_write_request_defaults(self) -> None:
        m = SavedScanWriteRequest.model_validate({"name": "x"})
        assert m.skip_enrichment is False
        assert m.repo_ids == []
        assert m.tool_names == []
        assert m.skip_tool_ids == []
        assert m.segments == []
        assert m.arg_profile_ids == []

    def test_write_request_skip_tool_ids_camel_and_snake(self) -> None:
        camel = SavedScanWriteRequest.model_validate(
            {"name": "x", "skipToolIds": ["xsstrike"]}
        )
        snake = SavedScanWriteRequest.model_validate(
            {"name": "x", "skip_tool_ids": ["xsstrike"]}
        )
        assert camel.skip_tool_ids == ["xsstrike"]
        assert snake.skip_tool_ids == ["xsstrike"]

    def test_write_request_segments(self) -> None:
        m = SavedScanWriteRequest.model_validate(
            {"name": "x", "segments": ["sast", "secrets"]}
        )
        assert m.segments == ["sast", "secrets"]

    def test_write_request_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            SavedScanWriteRequest.model_validate({"name": ""})

    def test_write_request_extra_ignored(self) -> None:
        m = SavedScanWriteRequest.model_validate({"name": "x", "createdAt": "ignored"})
        assert not hasattr(m, "createdAt")

    def test_list_item_response_serialization(self) -> None:
        r = SavedScanListItemResponse(
            id=3,
            name="Weekly",
            skip_enrichment=False,
            repo_ids=[1, 2],
            tool_names=["gitleaks"],
            skip_tool_ids=["xsstrike"],
            segments=["sast", "secrets"],
            arg_profile_ids=[12],
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        wire = r.model_dump(by_alias=True)
        assert wire["skipEnrichment"] is False
        assert wire["repoIds"] == [1, 2]
        assert wire["toolNames"] == ["gitleaks"]
        assert wire["skipToolIds"] == ["xsstrike"]
        assert wire["segments"] == ["sast", "secrets"]
        assert wire["argProfileIds"] == [12]
        assert wire["createdAt"].startswith("2026-")

    def test_list_response_envelope(self) -> None:
        env = SavedScanListResponse(
            items=[
                SavedScanListItemResponse(
                    id=1,
                    name="A",
                    skip_enrichment=False,
                    repo_ids=[],
                    tool_names=["x"],
                    skip_tool_ids=[],
                    segments=[],
                    arg_profile_ids=[],
                    created_at="t",
                    updated_at="t",
                )
            ],
            total=1,
            offset=0,
            limit=50,
        )
        wire = env.model_dump(by_alias=True)
        assert wire["total"] == 1
        assert wire["items"][0]["toolNames"] == ["x"]

    def test_detail_response_serialization(self) -> None:
        d = SavedScanDetailResponse(
            id=3,
            name="Weekly secrets sweep",
            skip_enrichment=False,
            repos=[
                SavedScanRepoResponse(id=1, name="auth-service", deleted_at=None),
                SavedScanRepoResponse(
                    id=2, name="payments", deleted_at="2026-01-01T00:00:00Z"
                ),
            ],
            tools=[SavedScanToolResponse(tool_name="gitleaks")],
            skip_tool_ids=["xsstrike"],
            segments=["sast", "sca", "secrets"],
            arg_profiles=[
                SavedScanArgProfileResponse(
                    id=12, tool_name="gitleaks", name="verbose-scan"
                )
            ],
            created_at="2026-05-03T12:00:00Z",
            updated_at="2026-05-03T12:00:00Z",
        )
        wire = d.model_dump(by_alias=True)
        assert wire["skipEnrichment"] is False
        assert wire["repos"][0]["deletedAt"] is None
        assert wire["repos"][1]["deletedAt"] == "2026-01-01T00:00:00Z"
        assert wire["tools"] == [{"toolName": "gitleaks"}]
        assert wire["skipToolIds"] == ["xsstrike"]
        assert wire["segments"] == ["sast", "sca", "secrets"]
        assert wire["argProfiles"][0]["toolName"] == "gitleaks"

    def test_stale_details_discriminated_union(self) -> None:
        d = StaleSavedScanDetails(
            stale_items=[
                StaleSavedScanRepoItemDetail(id=5, name="deleted-repo"),
                StaleSavedScanToolItemDetail(name="old-tool"),
                StaleSavedScanArgProfileItemDetail(id=99),
            ]
        )
        wire = d.model_dump(by_alias=True)
        assert wire["staleItems"][0] == {
            "kind": "repo",
            "id": 5,
            "name": "deleted-repo",
        }
        assert wire["staleItems"][1] == {"kind": "tool", "name": "old-tool"}
        assert wire["staleItems"][2] == {"kind": "argProfile", "id": 99}

    def test_stale_repo_item_allows_null_name(self) -> None:
        item = StaleSavedScanRepoItemDetail(id=5, name=None)
        wire = item.model_dump(by_alias=True)
        assert wire == {"kind": "repo", "id": 5, "name": None}
