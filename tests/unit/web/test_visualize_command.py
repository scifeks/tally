"""Tests for findings visualize command lifecycle and --stop behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.findings_commands import FindingsCommands


def _make_repl_mock(active_project: str | None = "testproject") -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/tally_test"
    repl.config.global_config_path = "/nonexistent/global.json"
    return repl


class TestStopCommand:
    def test_stop_with_no_server_prints_message(self, capsys) -> None:
        cmds = FindingsCommands(_make_repl_mock())
        cmds._cmd_stop()
        assert "No web UI server is currently running" in capsys.readouterr().out

    def test_stop_sets_should_exit_true(self) -> None:
        cmds = FindingsCommands(_make_repl_mock())
        server_mock = MagicMock()
        cmds._server = server_mock
        cmds._cmd_stop()
        assert server_mock.should_exit is True

    def test_stop_clears_server_reference(self) -> None:
        cmds = FindingsCommands(_make_repl_mock())
        cmds._server = MagicMock()
        cmds._cmd_stop()
        assert cmds._server is None

    def test_stop_dispatched_via_cmd_findings(self, capsys) -> None:
        cmds = FindingsCommands(_make_repl_mock())
        cmds.cmd_findings("findings", ["visualize", "--stop"])
        assert "No web UI server is currently running" in capsys.readouterr().out


class TestVisualizeCommand:
    def test_no_active_project_prints_error(self, capsys) -> None:
        cmds = FindingsCommands(_make_repl_mock(active_project=None))
        cmds.cmd_visualize([])
        assert "No active project" in capsys.readouterr().out

    def test_already_running_prints_error(self, capsys) -> None:
        cmds = FindingsCommands(_make_repl_mock())
        cmds._server = MagicMock()
        cmds.cmd_visualize([])
        assert "already running" in capsys.readouterr().out

    @patch("application.repl.commands.findings_commands.web_server.create_server")
    @patch("application.repl.commands.findings_commands.threading.Thread")
    def test_visualize_returns_promptly_when_server_starts(
        self, mock_thread_cls, mock_create_server, capsys
    ) -> None:
        """Command must return as soon as server.started is True."""
        server_mock = MagicMock()
        server_mock.started = True
        mock_create_server.return_value = server_mock

        cmds = FindingsCommands(_make_repl_mock())
        cmds.cmd_visualize([])

        out = capsys.readouterr().out
        assert "running at" in out
        assert cmds._server is server_mock

    @patch("application.repl.commands.findings_commands.web_server.create_server")
    @patch("application.repl.commands.findings_commands.threading.Thread")
    @patch("application.repl.commands.findings_commands.time.monotonic")
    @patch("application.repl.commands.findings_commands.time.sleep")
    def test_visualize_prints_error_if_server_fails_to_start(
        self,
        mock_sleep,
        mock_monotonic,
        mock_thread_cls,
        mock_create_server,
        capsys,
    ) -> None:
        """Prints an error and clears server state if the port is unavailable."""
        server_mock = MagicMock()
        server_mock.started = False
        mock_create_server.return_value = server_mock
        # First call sets deadline (0.0 + 2.0 = 2.0); second enters while;
        # third exceeds deadline and exits the loop.
        mock_monotonic.side_effect = [0.0, 0.0, 3.0]

        cmds = FindingsCommands(_make_repl_mock())
        cmds.cmd_visualize([])

        out = capsys.readouterr().out
        assert "already in use" in out or "failed to start" in out
        assert cmds._server is None

    def test_stop_flag_short_circuits_start(self, capsys) -> None:
        """--stop passed to cmd_visualize must not attempt server startup."""
        cmds = FindingsCommands(_make_repl_mock())
        cmds.cmd_visualize(["--stop"])
        assert "No web UI server is currently running" in capsys.readouterr().out
