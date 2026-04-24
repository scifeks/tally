"""Tests for UiCommands (ui serve) lifecycle and --stop behaviour."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.ui_commands import UiCommands


def _make_global_config(
    host: str = "127.0.0.1",
    api_port: int = 8080,
    vite_port: int = 3000,
    allowed_origins: list[str] | None = None,
) -> MagicMock:
    cfg = MagicMock()
    cfg.web_ui_host = host
    cfg.web_ui_port = api_port
    cfg.web_ui_vite_port = vite_port
    cfg.effective_allowed_origins = (
        allowed_origins
        if allowed_origins is not None
        else [f"http://{host}:{vite_port}"]
    )
    return cfg


def _make_repl_mock(
    active_project: str | None = "testproject",
    base_path: str = "/tmp/tally_test",
    host: str = "127.0.0.1",
) -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = base_path
    repl.config.global_config = _make_global_config(host=host)
    return repl


def _make_cmds(
    active_project: str | None = "testproject",
    base_path: str = "/tmp/tally_test",
) -> UiCommands:
    return UiCommands(
        _make_repl_mock(active_project, base_path),
        server_factory=MagicMock(),
    )


class TestStopCommand:
    def test_stop_with_no_server_prints_message(self, capsys) -> None:
        cmds = _make_cmds()
        cmds._cmd_stop()
        assert "No UI servers" in capsys.readouterr().out

    def test_stop_sets_should_exit_true(self) -> None:
        cmds = _make_cmds()
        server_mock = MagicMock()
        cmds._server = server_mock
        cmds._cmd_stop()
        assert server_mock.should_exit is True

    def test_stop_clears_server_reference(self) -> None:
        cmds = _make_cmds()
        cmds._server = MagicMock()
        cmds._cmd_stop()
        assert cmds._server is None

    def test_stop_terminates_vite_process(self) -> None:
        cmds = _make_cmds()
        vite_mock = MagicMock()
        cmds._vite_proc = vite_mock
        cmds._cmd_stop()
        vite_mock.terminate.assert_called_once()
        assert cmds._vite_proc is None

    def test_stop_dispatched_via_cmd_ui(self, capsys) -> None:
        cmds = _make_cmds()
        cmds.cmd_ui("ui", ["serve", "--stop"])
        assert "No UI servers" in capsys.readouterr().out


class TestServeCommand:
    def test_no_active_project_prints_error(self, capsys) -> None:
        cmds = _make_cmds(active_project=None)
        cmds.cmd_serve([])
        assert "No active project" in capsys.readouterr().out

    def test_already_running_prints_error(self, capsys) -> None:
        cmds = _make_cmds()
        cmds._server = MagicMock()
        cmds.cmd_serve([])
        assert "already running" in capsys.readouterr().out

    def test_banned_host_prints_error(self, capsys) -> None:
        repl = _make_repl_mock()
        repl.config.global_config = _make_global_config(host="0.0.0.0")
        cmds = UiCommands(repl, server_factory=MagicMock())
        cmds.cmd_serve([])
        assert "all interfaces" in capsys.readouterr().out

    def test_missing_ui_dir_prints_error(self, capsys, tmp_path) -> None:
        cmds = _make_cmds(base_path=str(tmp_path))
        cmds.cmd_serve([])
        assert "UI directory not found" in capsys.readouterr().out

    @patch("application.repl.commands.ui_commands.UiCommands._wait_for_port")
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    @patch("application.repl.commands.ui_commands.threading.Thread")
    def test_serve_starts_server_on_success(
        self, mock_thread_cls, mock_start_vite, mock_wait, tmp_path, capsys
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        server_mock = MagicMock()
        server_mock.started = True
        factory = MagicMock(return_value=server_mock)
        mock_wait.return_value = True

        repl = _make_repl_mock(base_path=str(tmp_path))
        cmds = UiCommands(repl, server_factory=factory)
        cmds.cmd_serve([])

        assert cmds._server is server_mock
        out = capsys.readouterr().out
        assert "running at" in out

    @patch("application.repl.commands.ui_commands.threading.Thread")
    @patch("application.repl.commands.ui_commands.time.monotonic")
    @patch("application.repl.commands.ui_commands.time.sleep")
    def test_serve_prints_error_if_api_server_fails(
        self, mock_sleep, mock_monotonic, mock_thread_cls, tmp_path, capsys
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        server_mock = MagicMock()
        server_mock.started = False
        factory = MagicMock(return_value=server_mock)
        mock_monotonic.side_effect = [0.0, 0.0, 3.0]

        repl = _make_repl_mock(base_path=str(tmp_path))
        cmds = UiCommands(repl, server_factory=factory)
        cmds.cmd_serve([])

        out = capsys.readouterr().out
        assert "already in use" in out or "failed to start" in out
        assert cmds._server is None

    def test_stop_flag_short_circuits_start(self, capsys) -> None:
        cmds = _make_cmds()
        cmds.cmd_serve(["--stop"])
        assert "No UI servers" in capsys.readouterr().out


class TestWriteEnvLocal:
    def test_writes_expected_content(self, tmp_path) -> None:
        UiCommands._write_env_local(tmp_path, "127.0.0.1", 8080, 3000)
        content = (tmp_path / ".env.local").read_text()
        assert "TALLY_HOST=127.0.0.1" in content
        assert "TALLY_VITE_PORT=3000" in content
        assert "VITE_API_BASE_URL=http://127.0.0.1:8080" in content

    def test_atomic_write_no_tmp_leftover(self, tmp_path) -> None:
        UiCommands._write_env_local(tmp_path, "127.0.0.1", 8080, 3000)
        assert (tmp_path / ".env.local").exists()
        assert not (tmp_path / ".env.local.tmp").exists()

    def test_overwrite_replaces_previous(self, tmp_path) -> None:
        UiCommands._write_env_local(tmp_path, "127.0.0.1", 8080, 3000)
        UiCommands._write_env_local(tmp_path, "localhost", 9090, 5173)
        content = (tmp_path / ".env.local").read_text()
        assert "TALLY_HOST=localhost" in content
        assert "TALLY_VITE_PORT=5173" in content
        assert "VITE_API_BASE_URL=http://localhost:9090" in content
        assert "127.0.0.1" not in content
