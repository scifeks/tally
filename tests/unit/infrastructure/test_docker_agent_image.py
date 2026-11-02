"""Unit tests for DockerAgentImage adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.agent_sandbox.image import (
    AgentImageBuildError,
    DockerNotAvailableError,
)
from infrastructure.docker.agent_image import DockerAgentImage

_SUB_RUN = "infrastructure.docker.agent_image.subprocess.run"


class TestImageExists:
    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerAgentImage().image_exists("img:latest")

    def test_image_exists_when_docker_inspect_succeeds(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)):
            result = DockerAgentImage().image_exists("tally/triage-agent")
        assert result is True


class TestBuildImage:
    def test_build_image_succeeds(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)):
            DockerAgentImage().build_image("tag", Path("/ctx"))

    def test_raises_on_failure(self) -> None:
        result = MagicMock(returncode=1, stderr="build error")
        with (
            patch(_SUB_RUN, return_value=result),
            pytest.raises(AgentImageBuildError, match="build error"),
        ):
            DockerAgentImage().build_image("tag", Path("/ctx"))

    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerAgentImage().build_image("tag", Path("/ctx"))


class TestRemoveContainers:
    def test_removes_matched_containers(self) -> None:
        ps_result = MagicMock(returncode=0, stdout="abc123\ndef456\n")
        rm_result = MagicMock(returncode=0)
        with patch(_SUB_RUN, side_effect=[ps_result, rm_result, rm_result]):
            DockerAgentImage().remove_containers("img:latest")

    def test_noop_when_no_containers(self) -> None:
        ps_result = MagicMock(returncode=0, stdout="")
        with patch(_SUB_RUN, side_effect=[ps_result]):
            DockerAgentImage().remove_containers("img:latest")

    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerAgentImage().remove_containers("img:latest")
