"""Unit tests for arg-profile request and response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from web.api.arg_profiles_schemas import (
    ArgProfileFileArgResponse,
    ArgProfileFlagArgResponse,
    ArgProfileInUseDetails,
    ArgProfileListResponse,
    ArgProfilePayload,
    ArgProfilePayloadFileArg,
    ArgProfilePayloadFlagArg,
    ArgProfilePayloadStringArg,
    ArgProfileResponse,
    ArgProfileStringArgResponse,
    parse_arg_profile_payload,
)


class TestArgProfilesSchemas:
    def test_payload_parses_three_arg_kinds(self) -> None:
        payload = {
            "toolName": "gitleaks",
            "name": "verbose-scan",
            "args": [
                {"name": "--verbose", "type": "flag"},
                {"name": "--config", "type": "string", "value": ".gitleaks.toml"},
                {"name": "--rules", "type": "file"},
            ],
        }
        m = ArgProfilePayload.model_validate(payload)
        assert m.tool_name == "gitleaks"
        assert m.name == "verbose-scan"
        assert len(m.args) == 3
        assert isinstance(m.args[0], ArgProfilePayloadFlagArg)
        assert isinstance(m.args[1], ArgProfilePayloadStringArg)
        assert m.args[1].value == ".gitleaks.toml"
        assert isinstance(m.args[2], ArgProfilePayloadFileArg)

    def test_payload_snake_case_alias(self) -> None:
        m = ArgProfilePayload.model_validate(
            {
                "tool_name": "gitleaks",
                "name": "x",
                "args": [{"name": "--v", "type": "flag"}],
            }
        )
        assert m.tool_name == "gitleaks"

    def test_payload_string_arg_requires_value(self) -> None:
        with pytest.raises(ValidationError):
            ArgProfilePayload.model_validate(
                {
                    "toolName": "x",
                    "name": "y",
                    "args": [{"name": "--c", "type": "string"}],
                }
            )

    def test_payload_file_arg_rejects_extra_value(self) -> None:
        m = ArgProfilePayload.model_validate(
            {
                "toolName": "x",
                "name": "y",
                "args": [{"name": "--r", "type": "file", "value": "ignored"}],
            }
        )
        assert isinstance(m.args[0], ArgProfilePayloadFileArg)
        assert not hasattr(m.args[0], "value")

    def test_payload_unknown_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ArgProfilePayload.model_validate(
                {
                    "toolName": "x",
                    "name": "y",
                    "args": [{"name": "--z", "type": "blob"}],
                }
            )

    def test_payload_empty_tool_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ArgProfilePayload.model_validate({"toolName": "", "name": "x", "args": []})

    def test_parse_helper_accepts_json_string(self) -> None:
        raw = '{"toolName":"gitleaks","name":"x","args":[{"name":"--v","type":"flag"}]}'
        m = parse_arg_profile_payload(raw)
        assert m.tool_name == "gitleaks"
        assert len(m.args) == 1

    def test_parse_helper_rejects_invalid_json(self) -> None:
        with pytest.raises(ValueError):
            parse_arg_profile_payload("{not json")

    def test_parse_helper_rejects_non_object(self) -> None:
        with pytest.raises(ValueError):
            parse_arg_profile_payload("[]")

    def test_parse_helper_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            parse_arg_profile_payload("")

    def test_response_serializes_camel_case(self) -> None:
        r = ArgProfileResponse(
            id=12,
            tool_name="gitleaks",
            name="verbose",
            args=[
                ArgProfileFlagArgResponse(name="--verbose"),
                ArgProfileStringArgResponse(name="--config", value=".gitleaks.toml"),
                ArgProfileFileArgResponse(
                    name="--rules",
                    path="arg_files/12/--rules.yml",
                    download_url="/api/v1/projects/1/arg-profiles/12/files/--rules",
                ),
            ],
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )
        wire = r.model_dump(by_alias=True)
        assert wire["toolName"] == "gitleaks"
        assert wire["createdAt"] == "2026-05-04T00:00:00Z"
        assert wire["args"][2]["downloadUrl"].endswith("/files/--rules")
        assert wire["args"][0] == {"name": "--verbose", "type": "flag"}

    def test_response_file_arg_serializes_original_filename(
        self,
    ) -> None:
        r = ArgProfileFileArgResponse(
            name="--rules",
            path="arg_files/1/--rules",
            original_filename="custom_rules.yml",
        )
        wire = r.model_dump(by_alias=True)
        assert wire["originalFilename"] == "custom_rules.yml"

    def test_response_file_arg_omits_download_url_when_none(self) -> None:
        r = ArgProfileResponse(
            id=1,
            tool_name="t",
            name="n",
            args=[ArgProfileFileArgResponse(name="--r", path="arg_files/1/--r")],
            created_at="x",
            updated_at="x",
        )
        wire = r.model_dump(by_alias=True)
        assert wire["args"][0]["downloadUrl"] is None

    def test_list_response_envelope(self) -> None:
        env = ArgProfileListResponse(
            items=[
                ArgProfileResponse(
                    id=1,
                    tool_name="t",
                    name="n",
                    args=[],
                    created_at="x",
                    updated_at="x",
                )
            ],
            total=1,
            offset=0,
            limit=50,
        )
        wire = env.model_dump(by_alias=True)
        assert wire["items"][0]["toolName"] == "t"

    def test_in_use_details(self) -> None:
        d = ArgProfileInUseDetails(
            saved_scan_ids=[3, 5],
            saved_scan_names=["Weekly", "Deep"],
        )
        wire = d.model_dump(by_alias=True)
        assert wire["savedScanIds"] == [3, 5]
        assert wire["savedScanNames"] == ["Weekly", "Deep"]
