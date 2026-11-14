"""Unit tests for infrastructure.docker.triage_container."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from application.triage.container import (
    DockerNotAvailableError,
    TriageContainerStartError,
)
from infrastructure.docker.triage_container import DockerTriageContainer

_RUN = "infrastructure.docker.triage_container.subprocess.run"


@pytest.fixture()
def adapter() -> DockerTriageContainer:
    return DockerTriageContainer()


class TestIsRunning:
    def test_returns_false_when_compose_file_missing(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        assert adapter.is_running(tmp_path / "missing.yaml") is False

    def test_returns_true_when_services_running(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        compose.write_text("services: {}")
        mock_result = type("R", (), {"stdout": "abc123\n", "returncode": 0})()
        with patch(_RUN, return_value=mock_result):
            assert adapter.is_running(compose) is True

    def test_returns_false_when_no_services_running(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        compose.write_text("services: {}")
        mock_result = type("R", (), {"stdout": "", "returncode": 0})()
        with patch(_RUN, return_value=mock_result):
            assert adapter.is_running(compose) is False

    def test_raises_when_docker_missing(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        compose.write_text("services: {}")
        with (
            patch(_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            adapter.is_running(compose)


class TestUp:
    def test_calls_compose_up(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        mock_result = type("R", (), {"stdout": "", "stderr": "", "returncode": 0})()
        with patch(_RUN, return_value=mock_result):
            adapter.up(compose)

    def test_raises_on_nonzero_exit(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        mock_result = type(
            "R",
            (),
            {"stdout": "", "stderr": "failed", "returncode": 1},
        )()
        with (
            patch(_RUN, return_value=mock_result),
            pytest.raises(TriageContainerStartError, match="failed"),
        ):
            adapter.up(compose)

    def test_raises_when_docker_missing(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        with (
            patch(_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            adapter.up(compose)

    def test_up_includes_wait_flag(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        mock_result = type("R", (), {"stdout": "", "stderr": "", "returncode": 0})()
        with patch(_RUN, return_value=mock_result) as mock_run:
            adapter.up(compose)
        cmd = mock_run.call_args[0][0]
        assert "--wait" in cmd


class TestDown:
    def test_calls_compose_down(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        mock_result = type("R", (), {"stdout": "", "stderr": "", "returncode": 0})()
        with patch(_RUN, return_value=mock_result):
            adapter.down(compose)

    def test_ignores_nonzero_exit(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        mock_result = type(
            "R",
            (),
            {"stdout": "", "stderr": "warn", "returncode": 1},
        )()
        with patch(_RUN, return_value=mock_result):
            adapter.down(compose)

    def test_raises_when_docker_missing(
        self, adapter: DockerTriageContainer, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        with (
            patch(_RUN, side_effect=FileNotFoundError),
            pytest.raises(DockerNotAvailableError),
        ):
            adapter.down(compose)
