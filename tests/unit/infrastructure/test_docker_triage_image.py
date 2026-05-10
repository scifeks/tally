"""Unit tests for DockerTriageImage adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.container import (
    DockerNotAvailableError,
    TriageImageBuildError,
)
from infrastructure.docker.triage_image import DockerTriageImage

_SUB_RUN = "infrastructure.docker.triage_image.subprocess.run"


class TestImageExists:
    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerTriageImage().image_exists("img:latest")

    def test_image_exists_when_docker_inspect_succeeds(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)):
            result = DockerTriageImage().image_exists("tally/triage-agent")
        assert result is True


class TestBuildImage:
    def test_build_image_succeeds(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)):
            DockerTriageImage().build_image("tag", Path("/ctx"))

    def test_raises_on_failure(self) -> None:
        result = MagicMock(returncode=1, stderr="build error")
        with (
            patch(_SUB_RUN, return_value=result),
            pytest.raises(TriageImageBuildError, match="build error"),
        ):
            DockerTriageImage().build_image("tag", Path("/ctx"))

    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerTriageImage().build_image("tag", Path("/ctx"))


class TestRemoveContainers:
    def test_removes_matched_containers(self) -> None:
        ps_result = MagicMock(returncode=0, stdout="abc123\ndef456\n")
        rm_result = MagicMock(returncode=0)
        with patch(_SUB_RUN, side_effect=[ps_result, rm_result, rm_result]):
            DockerTriageImage().remove_containers("img:latest")

    def test_noop_when_no_containers(self) -> None:
        ps_result = MagicMock(returncode=0, stdout="")
        with patch(_SUB_RUN, side_effect=[ps_result]):
            DockerTriageImage().remove_containers("img:latest")

    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerTriageImage().remove_containers("img:latest")
