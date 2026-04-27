"""Tests for UiCommands (ui serve) lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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
        app_factory=MagicMock(),
    )


class TestServeCommand:
    @patch("uvicorn.run")
    @patch(
        "application.repl.commands.ui_commands.UiCommands._wait_for_port",
        return_value=False,
    )
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    def test_no_active_project_does_not_block_serve(
        self, _mock_start_vite, _mock_wait, _mock_uvicorn_run, tmp_path, capsys
    ) -> None:
        """ui serve works without an active REPL project — the SPA picks one."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        cmds = _make_cmds(active_project=None, base_path=str(tmp_path))
        cmds.cmd_serve([])
        assert "No active project" not in capsys.readouterr().out

    def test_banned_host_prints_error(self, capsys) -> None:
        repl = _make_repl_mock()
        repl.config.global_config = _make_global_config(host="0.0.0.0")
        cmds = UiCommands(repl, app_factory=MagicMock())
        cmds.cmd_serve([])
        assert "all interfaces" in capsys.readouterr().out

    def test_missing_ui_dir_prints_error(self, capsys, tmp_path) -> None:
        cmds = _make_cmds(base_path=str(tmp_path))
        cmds.cmd_serve([])
        assert "UI directory not found" in capsys.readouterr().out

    @patch("uvicorn.run")
    @patch("application.repl.commands.ui_commands.UiCommands._wait_for_port")
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    def test_serve_starts_server_on_success(
        self, _mock_start_vite, mock_wait, mock_uvicorn_run, tmp_path, capsys
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        app_mock = MagicMock()
        factory = MagicMock(return_value=app_mock)
        mock_wait.return_value = True

        repl = _make_repl_mock(base_path=str(tmp_path))
        cmds = UiCommands(repl, app_factory=factory)
        with patch("webbrowser.open"):
            cmds.cmd_serve([])

        mock_uvicorn_run.assert_called_once_with(
            app_mock, host="127.0.0.1", port=8080, log_level="warning"
        )
        assert "running at" in capsys.readouterr().out

    @patch("uvicorn.run", side_effect=OSError("address already in use"))
    @patch("application.repl.commands.ui_commands.UiCommands._wait_for_port")
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    def test_serve_prints_error_if_api_server_fails(
        self, _mock_start_vite, _mock_wait, _mock_uvicorn_run, tmp_path, capsys
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        repl = _make_repl_mock(base_path=str(tmp_path))
        cmds = UiCommands(repl, app_factory=MagicMock())
        cmds.cmd_serve([])
        out = capsys.readouterr().out
        assert "already in use" in out or "failed to start" in out

    @patch("uvicorn.run")
    @patch("application.repl.commands.ui_commands.UiCommands._wait_for_port")
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    def test_cmd_serve_blocks_on_main_thread(
        self, _mock_start_vite, _mock_wait, mock_uvicorn_run, tmp_path
    ) -> None:
        """cmd_serve calls uvicorn.run directly — no daemon thread for the server."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        cmds = _make_cmds(base_path=str(tmp_path))
        cmds.cmd_serve([])
        mock_uvicorn_run.assert_called_once()

    @patch(
        "application.repl.commands.ui_commands.UiCommands._wait_for_port",
        return_value=False,
    )
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    @patch("uvicorn.run", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_propagates(
        self, _mock_uvicorn_run, _mock_start_vite, _mock_wait, tmp_path
    ) -> None:
        """KeyboardInterrupt from uvicorn propagates to the REPL caller."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        cmds = _make_cmds(base_path=str(tmp_path))
        with pytest.raises(KeyboardInterrupt):
            cmds.cmd_serve([])

    @patch(
        "application.repl.commands.ui_commands.UiCommands._wait_for_port",
        return_value=False,
    )
    @patch("application.repl.commands.ui_commands.subprocess.Popen")
    @patch("application.repl.commands.ui_commands.atexit.register")
    @patch("uvicorn.run")
    def test_atexit_hook_registered_for_vite(
        self,
        _mock_uvicorn_run,
        mock_atexit,
        mock_popen,
        _mock_wait,
        tmp_path,
    ) -> None:
        """_start_vite registers atexit hook for Vite subprocess teardown."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        mock_popen.return_value = MagicMock()
        cmds = _make_cmds(base_path=str(tmp_path))
        cmds.cmd_serve([])
        mock_atexit.assert_called_once_with(cmds._stop_vite)

    @patch("uvicorn.run")
    @patch("application.repl.commands.ui_commands.UiCommands._wait_for_port")
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    def test_stop_flag_no_longer_recognized(
        self, _mock_start_vite, _mock_wait, mock_uvicorn_run, tmp_path
    ) -> None:
        """Passing --stop no longer short-circuits; serve proceeds normally."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        cmds = _make_cmds(base_path=str(tmp_path))
        cmds.cmd_serve(["--stop"])
        mock_uvicorn_run.assert_called_once()

    def test_ui_stop_method_removed(self) -> None:
        assert not hasattr(UiCommands, "_cmd_stop")

    def test_help_text_drops_stop(self, capsys) -> None:
        cmds = _make_cmds()
        cmds._show_help()
        assert "--stop" not in capsys.readouterr().out

    def test_cmd_serve_help_includes_ctrl_c_message(self) -> None:
        assert "Press Ctrl+C to stop the server." in (
            UiCommands.cmd_serve.__doc__ or ""
        )

    @patch(
        "application.repl.commands.ui_commands.UiCommands._wait_for_port",
        return_value=False,
    )
    @patch("application.repl.commands.ui_commands.UiCommands._start_vite")
    def test_cmd_serve_prints_runtime_banner(
        self, _mock_start_vite, _mock_wait, tmp_path, capsys
    ) -> None:
        """Banner is printed before uvicorn.run is invoked."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        printed_before_run: list[str] = []

        def capture_run(*args: object, **kwargs: object) -> None:
            printed_before_run.append(capsys.readouterr().out)

        with patch("uvicorn.run", side_effect=capture_run):
            cmds = _make_cmds(base_path=str(tmp_path))
            cmds.cmd_serve([])

        assert printed_before_run, "uvicorn.run was not called"
        assert "Press Ctrl+C" in printed_before_run[0]


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
