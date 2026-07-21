"""Unit tests for shell metacharacter validation on tool config schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.schemas.command_entry import CommandEntry
from core.config.schemas.docker_container import DockerContainer


class TestCommandEntryMetacharValidation:
    @pytest.mark.parametrize(
        "path",
        [
            "cd && python -m pip_audit",
            "/usr/bin/tool;echo pwned",
            "tool|cat",
            "path`cmd`",
            "$HOME/tool",
            "tool>output",
        ],
    )
    def test_rejects_path_with_metacharacters(self, path: str) -> None:
        with pytest.raises(ValidationError, match="metacharacter"):
            CommandEntry(type="repo", location="local", path=path)

    def test_accepts_clean_local_path(self) -> None:
        entry = CommandEntry(
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
        )
        assert entry.path == "/usr/bin/semgrep"

    def test_accepts_empty_path_for_docker(self) -> None:
        entry = CommandEntry(
            type="repo",
            location="docker",
            container=DockerContainer(
                name="runner",
                tool_path="/usr/bin/tool",
            ),
        )
        assert entry.path == ""


class TestDockerContainerMetacharValidation:
    def test_rejects_name_with_metacharacters(
        self,
    ) -> None:
        with pytest.raises(ValidationError, match="metacharacter"):
            DockerContainer(
                name="container;evil",
                tool_path="/usr/bin/tool",
            )

    def test_rejects_tool_path_with_metacharacters(
        self,
    ) -> None:
        with pytest.raises(ValidationError, match="metacharacter"):
            DockerContainer(
                name="runner",
                tool_path="/bin/tool && evil",
            )

    def test_accepts_clean_container(self) -> None:
        c = DockerContainer(
            name="my-runner",
            tool_path="/usr/bin/semgrep",
        )
        assert c.name == "my-runner"
        assert c.tool_path == "/usr/bin/semgrep"
