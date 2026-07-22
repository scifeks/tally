"""Unit tests for Docker SCA tool override offering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.project_commands import (
    _offer_docker_sca_overrides,
)
from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import Repository


def _docker_repo(
    repo_id: int = 1,
    container: str = "my-app",
    docker_path: str = "/app",
    languages: list[str] | None = None,
    service_name: str = "default",
) -> Repository:
    service = RepoService(
        name=service_name,
        container_name=container,
        docker_path=docker_path,
        languages=languages or ["python"],
    )
    return Repository(
        id=repo_id,
        name="test-repo",
        path="/tmp/repo",
        services=[service],
    )


def _local_repo(repo_id: int = 1) -> Repository:
    service = RepoService(name="default", languages=["python"])
    return Repository(
        id=repo_id,
        name="local-repo",
        path="/tmp/repo",
        services=[service],
    )


@pytest.fixture()
def _mock_probe():
    with patch(
        "application.repl.commands.project_commands.probe_container_tools"
    ) as mock:
        yield mock


@pytest.fixture()
def _mock_overrides():
    with patch(
        "application.repl.commands.project_commands.ToolOverridesService"
    ) as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture()
def _mock_repo_factory():
    with patch(
        "application.repl.commands.project_commands.create_overrides_repo"
    ) as mock:
        yield mock


class TestOfferDockerScaOverrides:
    def test_skips_local_repo(self, _mock_probe, capsys) -> None:
        _offer_docker_sca_overrides("proj", "/base", _local_repo())
        _mock_probe.assert_not_called()

    def test_skips_repo_without_id(self, _mock_probe) -> None:
        repo = _docker_repo()
        repo = Repository(
            name="r",
            path="/tmp/r",
            services=repo.services,
        )
        _offer_docker_sca_overrides("proj", "/base", repo)
        _mock_probe.assert_not_called()

    def test_prints_message_when_no_tools_detected(
        self, _mock_probe, _mock_repo_factory, capsys
    ) -> None:
        _mock_probe.return_value = {}
        _offer_docker_sca_overrides("proj", "/base", _docker_repo())
        assert "No SCA tools" in capsys.readouterr().out

    @patch("builtins.input", return_value="y")
    def test_creates_override_on_accept(
        self,
        _input,
        _mock_probe,
        _mock_overrides,
        _mock_repo_factory,
    ) -> None:
        _mock_probe.return_value = {"pip-audit": "/usr/local/bin/pip-audit"}
        _offer_docker_sca_overrides("proj", "/base", _docker_repo())
        _mock_overrides.create.assert_called_once_with(
            tool_name="pip-audit",
            args_mode="stock",
            type="repo",
            location="docker",
            container_name="my-app",
            container_tool_path="/usr/local/bin/pip-audit",
            scope="service",
            repo_id=1,
            service_name="default",
        )

    @patch("builtins.input", return_value="n")
    def test_skips_override_on_decline(
        self,
        _input,
        _mock_probe,
        _mock_overrides,
        _mock_repo_factory,
    ) -> None:
        _mock_probe.return_value = {"pip-audit": "/usr/local/bin/pip-audit"}
        _offer_docker_sca_overrides("proj", "/base", _docker_repo())
        _mock_overrides.create.assert_not_called()

    @patch("builtins.input", return_value="y")
    def test_continues_on_create_error(
        self,
        _input,
        _mock_probe,
        _mock_overrides,
        _mock_repo_factory,
        capsys,
    ) -> None:
        from application.tool_overrides.service import (
            ToolOverrideValidationError,
        )

        _mock_probe.return_value = {
            "pip-audit": "/usr/local/bin/pip-audit",
            "npm-audit": "/usr/bin/npm",
        }
        _mock_overrides.create.side_effect = [
            ToolOverrideValidationError([]),
            MagicMock(),
        ]
        _offer_docker_sca_overrides(
            "proj",
            "/base",
            _docker_repo(languages=["python", "node"]),
        )
        assert _mock_overrides.create.call_count == 2
