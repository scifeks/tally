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
    def test_returns_true_on_zero_exit(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)):
            assert DockerTriageImage().image_exists("img:latest") is True

    def test_returns_false_on_nonzero_exit(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=1)):
            assert DockerTriageImage().image_exists("img:latest") is False

    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerTriageImage().image_exists("img:latest")

    def test_argv_shape(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)) as m:
            DockerTriageImage().image_exists("tally/triage-agent")
        argv = m.call_args[0][0]
        assert argv == ["docker", "image", "inspect", "tally/triage-agent"]


class TestBuildImage:
    def test_calls_docker_build(self) -> None:
        with patch(_SUB_RUN, return_value=MagicMock(returncode=0)) as m:
            DockerTriageImage().build_image("tag", Path("/ctx"))
        argv = m.call_args[0][0]
        assert argv == ["docker", "build", "-t", "tag", "/ctx"]

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
        with patch(_SUB_RUN, side_effect=[ps_result, rm_result, rm_result]) as m:
            DockerTriageImage().remove_containers("img:latest")
        calls = m.call_args_list
        assert calls[0][0][0] == [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "ancestor=img:latest",
        ]
        assert calls[1][0][0] == ["docker", "rm", "-f", "abc123"]
        assert calls[2][0][0] == ["docker", "rm", "-f", "def456"]

    def test_noop_when_no_containers(self) -> None:
        ps_result = MagicMock(returncode=0, stdout="")
        with patch(_SUB_RUN, side_effect=[ps_result]) as m:
            DockerTriageImage().remove_containers("img:latest")
        assert m.call_count == 1

    def test_raises_on_missing_docker(self) -> None:
        with (
            patch(_SUB_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            DockerTriageImage().remove_containers("img:latest")
