"""Unit tests for container lifecycle functions in application.triage.container."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.container import (
    DockerNotAvailableError,
    TriageContainerStartError,
    ensure_triage_containers,
    teardown_triage_containers,
    triage_containers_running,
)

_CONTAINER_PORT = "application.triage.container._resolve_container_port"
_COMPOSE_PATH = "application.triage.container._compose_path"
_GENERATE = "application.triage.compose.generate_triage_compose"
_RESOLVE_CONFIG = "application.triage.factory.resolve_triage_config"


@pytest.fixture()
def mock_port() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def fake_compose(tmp_path: Path) -> Path:
    p = tmp_path / "docker-compose.yaml"
    p.write_text("services: {}")
    return p


def _noop_generate(
    app_root: Path,
    repo_paths: dict[str, Path],
    **kwargs: object,
) -> None:
    """Mock generate that leaves the compose file unchanged."""


class TestTriageContainersRunning:
    def test_delegates_to_port(self, mock_port: MagicMock, fake_compose: Path) -> None:
        mock_port.is_running.return_value = True
        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=fake_compose),
        ):
            assert triage_containers_running(Path("/app")) is True


class TestEnsureTriageContainers:
    def test_returns_false_when_already_running_and_compose_unchanged(
        self, mock_port: MagicMock, fake_compose: Path
    ) -> None:
        mock_port.is_running.return_value = True
        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=fake_compose),
            patch(
                _RESOLVE_CONFIG,
                return_value=MagicMock(
                    provider_name="claude",
                    base_url="",
                    model="sonnet",
                ),
            ),
            patch(_GENERATE, side_effect=_noop_generate),
        ):
            assert ensure_triage_containers(Path("/app"), "proj") is False
        mock_port.up.assert_not_called()
        mock_port.down.assert_not_called()

    def test_restarts_when_compose_changed(
        self, mock_port: MagicMock, fake_compose: Path
    ) -> None:
        mock_port.is_running.return_value = True

        def _write_new_compose(*_args: object, **_kw: object) -> None:
            fake_compose.write_text("services: {updated: true}")

        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=fake_compose),
            patch(
                _RESOLVE_CONFIG,
                return_value=MagicMock(
                    provider_name="claude",
                    base_url="",
                    model="sonnet",
                ),
            ),
            patch(_GENERATE, side_effect=_write_new_compose),
        ):
            result = ensure_triage_containers(Path("/app"), "proj")

        assert result is True
        mock_port.down.assert_called_once()
        mock_port.up.assert_called_once()

    def test_generates_compose_and_starts(
        self, mock_port: MagicMock, fake_compose: Path
    ) -> None:
        mock_port.is_running.return_value = False

        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=fake_compose),
            patch(
                _RESOLVE_CONFIG,
                return_value=MagicMock(
                    provider_name="claude",
                    base_url="",
                    model="sonnet",
                ),
            ),
            patch(_GENERATE, side_effect=_noop_generate),
        ):
            result = ensure_triage_containers(Path("/app"), "proj")

        assert result is True
        mock_port.up.assert_called_once()

    def test_raises_docker_not_available(
        self, mock_port: MagicMock, fake_compose: Path
    ) -> None:
        mock_port.is_running.side_effect = DockerNotAvailableError("nope")
        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=fake_compose),
            patch(
                _RESOLVE_CONFIG,
                return_value=MagicMock(
                    provider_name="claude",
                    base_url="",
                    model="sonnet",
                ),
            ),
            patch(_GENERATE, side_effect=_noop_generate),
            pytest.raises(DockerNotAvailableError),
        ):
            ensure_triage_containers(Path("/app"), "proj")

    def test_raises_container_start_error(
        self, mock_port: MagicMock, fake_compose: Path
    ) -> None:
        mock_port.is_running.return_value = False
        mock_port.up.side_effect = TriageContainerStartError("boom")

        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=fake_compose),
            patch(
                _RESOLVE_CONFIG,
                return_value=MagicMock(
                    provider_name="claude",
                    base_url="",
                    model="sonnet",
                ),
            ),
            patch(_GENERATE, side_effect=_noop_generate),
            pytest.raises(TriageContainerStartError, match="boom"),
        ):
            ensure_triage_containers(Path("/app"), "proj")


class TestTeardownTriageContainers:
    def test_calls_down_when_file_exists(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        compose = tmp_path / "docker-compose.yaml"
        compose.write_text("services: {}")
        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=compose),
        ):
            teardown_triage_containers(Path("/app"))
        mock_port.down.assert_called_once()

    def test_skips_when_file_missing(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        compose = tmp_path / "missing.yaml"
        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=compose),
        ):
            teardown_triage_containers(Path("/app"))
        mock_port.down.assert_not_called()

    def test_swallows_exceptions(self, mock_port: MagicMock, tmp_path: Path) -> None:
        compose = tmp_path / "docker-compose.yaml"
        compose.write_text("services: {}")
        mock_port.down.side_effect = DockerNotAvailableError("nope")
        with (
            patch(_CONTAINER_PORT, return_value=mock_port),
            patch(_COMPOSE_PATH, return_value=compose),
        ):
            teardown_triage_containers(Path("/app"))
