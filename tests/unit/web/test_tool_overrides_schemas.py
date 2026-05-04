"""Unit tests for tool-override request and response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from web.api.tool_overrides_schemas import (
    ToolOverrideContainerRequest,
    ToolOverrideContainerResponse,
    ToolOverrideCreateRequest,
    ToolOverrideListResponse,
    ToolOverrideReplaceRequest,
    ToolOverrideResponse,
)


class TestToolOverridesSchemas:
    def test_create_local_round_trips_camel_and_snake(self) -> None:
        camel = {
            "toolName": "semgrep",
            "argsMode": "stock",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/semgrep",
        }
        snake = {
            "tool_name": "semgrep",
            "args_mode": "stock",
            "type": "repo",
            "location": "local",
            "path": "/usr/local/bin/semgrep",
        }
        m_camel = ToolOverrideCreateRequest.model_validate(camel)
        m_snake = ToolOverrideCreateRequest.model_validate(snake)
        assert m_camel.tool_name == "semgrep"
        assert m_snake.tool_name == "semgrep"
        assert m_camel.args_mode == "stock"
        assert m_camel.location == "local"
        assert m_camel.container is None

    def test_create_docker_with_container(self) -> None:
        m = ToolOverrideCreateRequest.model_validate(
            {
                "toolName": "semgrep",
                "argsMode": "custom",
                "type": "repo",
                "location": "docker",
                "container": {
                    "name": "tally-semgrep",
                    "toolPath": "/usr/local/bin/semgrep",
                },
            }
        )
        assert m.container is not None
        assert m.container.name == "tally-semgrep"
        assert m.container.tool_path == "/usr/local/bin/semgrep"

    def test_create_rejects_empty_tool_name(self) -> None:
        with pytest.raises(ValidationError):
            ToolOverrideCreateRequest.model_validate(
                {
                    "toolName": "",
                    "argsMode": "stock",
                    "type": "repo",
                    "location": "local",
                }
            )

    def test_create_extra_fields_ignored(self) -> None:
        m = ToolOverrideCreateRequest.model_validate(
            {
                "toolName": "semgrep",
                "argsMode": "stock",
                "type": "repo",
                "location": "local",
                "unknownField": "ignored",
            }
        )
        assert not hasattr(m, "unknownField")

    def test_replace_omits_tool_name_in_body(self) -> None:
        m = ToolOverrideReplaceRequest.model_validate(
            {
                "argsMode": "stock",
                "type": "api",
                "location": "local",
                "path": "/x",
            }
        )
        assert m.args_mode == "stock"
        assert m.tool_name is None

    def test_replace_with_matching_tool_name_in_body(self) -> None:
        m = ToolOverrideReplaceRequest.model_validate(
            {
                "toolName": "semgrep",
                "argsMode": "stock",
                "type": "repo",
                "location": "local",
                "path": "/x",
            }
        )
        assert m.tool_name == "semgrep"

    def test_response_serializes_camel_case(self) -> None:
        r = ToolOverrideResponse(
            id=7,
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="docker",
            path=None,
            container=ToolOverrideContainerResponse(
                name="tally-semgrep",
                tool_path="/usr/local/bin/semgrep",
            ),
        )
        wire = r.model_dump(by_alias=True)
        assert wire["toolName"] == "semgrep"
        assert wire["argsMode"] == "stock"
        assert wire["container"]["toolPath"] == "/usr/local/bin/semgrep"
        assert wire["path"] is None

    def test_list_response_envelope(self) -> None:
        items = [
            ToolOverrideResponse(
                id=1,
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="local",
                path="/x",
                container=None,
            )
        ]
        env = ToolOverrideListResponse(items=items, total=1, offset=0, limit=50)
        wire = env.model_dump(by_alias=True)
        assert wire["total"] == 1
        assert wire["items"][0]["toolName"] == "semgrep"

    def test_container_request_camel_alias(self) -> None:
        c = ToolOverrideContainerRequest.model_validate({"name": "x", "toolPath": "/y"})
        assert c.tool_path == "/y"
