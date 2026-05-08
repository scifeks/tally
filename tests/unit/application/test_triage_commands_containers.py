"""Tests for TriageCommands._ensure_containers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.triage_commands import TriageCommands
from application.triage.compose import ComposeGenerationError
from application.triage.container import (
    DockerNotAvailableError,
    TriageContainerStartError,
)

_RUNNING = "application.repl.commands.triage_commands.triage_containers_running"
_ENSURE = "application.repl.commands.triage_commands.ensure_triage_containers"


def _printed(repl: MagicMock) -> str:
    return " ".join(str(c) for c in repl.console.print.call_args_list)


@pytest.fixture()
def mock_repl() -> MagicMock:
    repl = MagicMock()
    repl.active_project = "test-project"
    return repl


class TestEnsureContainers:
    def test_returns_true_when_containers_started(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with (
            patch(_RUNNING, return_value=False),
            patch(_ENSURE, return_value=True),
        ):
            assert cmds._ensure_containers() is True
        printed = _printed(mock_repl)
        assert "Starting" in printed
        assert "ready" in printed.lower()

    def test_returns_true_silently_when_already_running(
        self, mock_repl: MagicMock
    ) -> None:
        cmds = TriageCommands(mock_repl)
        with (
            patch(_RUNNING, return_value=True),
            patch(_ENSURE, return_value=False),
        ):
            assert cmds._ensure_containers() is True
        printed = _printed(mock_repl)
        assert "Starting" not in printed
        assert "ready" not in printed.lower()

    def test_returns_false_on_docker_unavailable(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with patch(
            _RUNNING,
            side_effect=DockerNotAvailableError("no docker"),
        ):
            assert cmds._ensure_containers() is False
        assert "Docker" in _printed(mock_repl)

    def test_returns_false_on_compose_error(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with (
            patch(_RUNNING, return_value=False),
            patch(
                _ENSURE,
                side_effect=ComposeGenerationError("bad oauth"),
            ),
        ):
            assert cmds._ensure_containers() is False
        assert "bad oauth" in _printed(mock_repl)

    def test_returns_false_on_container_start_error(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with (
            patch(_RUNNING, return_value=False),
            patch(
                _ENSURE,
                side_effect=TriageContainerStartError("boom"),
            ),
        ):
            assert cmds._ensure_containers() is False
        assert "boom" in _printed(mock_repl)

    def test_returns_false_when_no_active_project(self, mock_repl: MagicMock) -> None:
        mock_repl.active_project = None
        cmds = TriageCommands(mock_repl)
        assert cmds._ensure_containers() is False
