"""Tests for triage --rebuild-container flag."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.repl.commands.triage_commands import TriageCommands
from application.triage.container import (
    DockerNotAvailableError,
    TriageImageBuildError,
)

_REBUILD_PATCH = "application.repl.commands.triage_commands.rebuild_triage_image"


def _printed(repl: MagicMock) -> str:
    return " ".join(str(c) for c in repl.console.print.call_args_list)


@pytest.fixture()
def mock_repl() -> MagicMock:
    repl = MagicMock()
    repl.active_project = None
    return repl


class TestRebuildContainer:
    def test_calls_rebuild_and_prints_success(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with patch(_REBUILD_PATCH) as mock_rebuild:
            cmds.cmd_triage("triage", ["--rebuild-container"])
        mock_rebuild.assert_called_once()
        assert "rebuilt" in _printed(mock_repl).lower()

    def test_does_not_require_active_project(self, mock_repl: MagicMock) -> None:
        mock_repl.active_project = None
        cmds = TriageCommands(mock_repl)
        with patch(_REBUILD_PATCH):
            cmds.cmd_triage("triage", ["--rebuild-container"])
        assert "No active" not in _printed(mock_repl)

    def test_prints_error_on_docker_not_available(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with patch(
            _REBUILD_PATCH,
            side_effect=DockerNotAvailableError("no docker"),
        ):
            cmds.cmd_triage("triage", ["--rebuild-container"])
        printed = _printed(mock_repl)
        assert "Docker" in printed
        assert "rebuilt" not in printed.lower()

    def test_prints_error_on_build_failure(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with patch(
            _REBUILD_PATCH,
            side_effect=TriageImageBuildError("build broke"),
        ):
            cmds.cmd_triage("triage", ["--rebuild-container"])
        printed = _printed(mock_repl)
        assert "build broke" in printed
        assert "rebuilt" not in printed.lower()

    def test_prints_error_on_missing_dockerfile(self, mock_repl: MagicMock) -> None:
        cmds = TriageCommands(mock_repl)
        with patch(
            _REBUILD_PATCH,
            side_effect=FileNotFoundError("Dockerfile not found"),
        ):
            cmds.cmd_triage("triage", ["--rebuild-container"])
        printed = _printed(mock_repl)
        assert "Dockerfile" in printed
        assert "rebuilt" not in printed.lower()
