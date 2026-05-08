"""Unit tests for application.triage.container."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.container import (
    TRIAGE_IMAGE_TAG,
    build_triage_image,
    ensure_triage_image,
    rebuild_triage_image,
    triage_image_ready,
)

_PORT_PATCH = "application.triage.container._resolve_image_port"


@pytest.fixture()
def mock_port() -> MagicMock:
    return MagicMock()


class TestTriageImageReady:
    def test_delegates_to_port(self, mock_port: MagicMock) -> None:
        mock_port.image_exists.return_value = True
        with patch(_PORT_PATCH, return_value=mock_port):
            assert triage_image_ready() is True
        mock_port.image_exists.assert_called_once_with(TRIAGE_IMAGE_TAG)

    def test_returns_false_when_missing(self, mock_port: MagicMock) -> None:
        mock_port.image_exists.return_value = False
        with patch(_PORT_PATCH, return_value=mock_port):
            assert triage_image_ready() is False


class TestBuildTriageImage:
    def test_calls_port_with_context_dir(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        dockerfile_dir = tmp_path / "docker" / "triage-agent"
        dockerfile_dir.mkdir(parents=True)
        (dockerfile_dir / "Dockerfile").write_text("FROM debian:12-slim")

        with patch(_PORT_PATCH, return_value=mock_port):
            build_triage_image(tmp_path)

        mock_port.build_image.assert_called_once_with(TRIAGE_IMAGE_TAG, dockerfile_dir)

    def test_raises_when_dockerfile_missing(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            pytest.raises(FileNotFoundError, match="Dockerfile not found"),
        ):
            build_triage_image(tmp_path)

        mock_port.build_image.assert_not_called()


class TestEnsureTriageImage:
    def test_returns_false_when_image_exists(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        mock_port.image_exists.return_value = True
        with patch(_PORT_PATCH, return_value=mock_port):
            assert ensure_triage_image(tmp_path) is False
        mock_port.build_image.assert_not_called()

    def test_builds_and_returns_true_when_missing(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        mock_port.image_exists.return_value = False
        dockerfile_dir = tmp_path / "docker" / "triage-agent"
        dockerfile_dir.mkdir(parents=True)
        (dockerfile_dir / "Dockerfile").write_text("FROM debian:12-slim")

        with patch(_PORT_PATCH, return_value=mock_port):
            assert ensure_triage_image(tmp_path) is True
        mock_port.build_image.assert_called_once()


class TestRebuildTriageImage:
    def test_removes_containers_then_builds(
        self, mock_port: MagicMock, tmp_path: Path
    ) -> None:
        dockerfile_dir = tmp_path / "docker" / "triage-agent"
        dockerfile_dir.mkdir(parents=True)
        (dockerfile_dir / "Dockerfile").write_text("FROM debian:12-slim")

        call_order: list[str] = []
        mock_port.remove_containers.side_effect = lambda *_: call_order.append("remove")
        mock_port.build_image.side_effect = lambda *_: call_order.append("build")

        with patch(_PORT_PATCH, return_value=mock_port):
            rebuild_triage_image(tmp_path)

        assert call_order == ["remove", "build"]
        mock_port.remove_containers.assert_called_once_with(TRIAGE_IMAGE_TAG)
        mock_port.build_image.assert_called_once_with(TRIAGE_IMAGE_TAG, dockerfile_dir)
