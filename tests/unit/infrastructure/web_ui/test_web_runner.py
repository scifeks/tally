"""Tests for WebUiRunner (the WebUiRunnerPort adapter)."""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from typing import TypedDict
from unittest.mock import MagicMock, patch

import pytest

from application.project.registry_service import ProjectRegistryService
from application.tools.registry import ToolRegistry
from infrastructure.web_ui.runner import WebUiRunner


@pytest.fixture(autouse=True)
def _block_killpg(monkeypatch):
    """Prevent any test from reaching the real os.killpg."""
    monkeypatch.setattr(
        "infrastructure.web_ui.runner.os.killpg",
        MagicMock(name="blocked_killpg"),
    )


class _ServeKwargs(TypedDict):
    base_path: str
    host: str
    api_port: int
    vite_port: int
    allowed_origins: list[str]
    project_registry: ProjectRegistryService
    tool_registry: ToolRegistry


def _serve_kwargs(
    base_path: str,
    host: str = "127.0.0.1",
    api_port: int = 8080,
    vite_port: int = 3000,
    allowed_origins: list[str] | None = None,
) -> _ServeKwargs:
    return {
        "base_path": base_path,
        "host": host,
        "api_port": api_port,
        "vite_port": vite_port,
        "allowed_origins": (
            allowed_origins
            if allowed_origins is not None
            else [f"https://{host}:{vite_port}"]
        ),
        "project_registry": MagicMock(spec=ProjectRegistryService),
        "tool_registry": ToolRegistry(),
    }


class TestServe:
    @patch("uvicorn.run")
    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_no_active_project_does_not_block_serve(
        self,
        _mock_start_vite,
        _mock_wait,
        _mock_uvicorn_run,
        tmp_path,
        capsys,
    ) -> None:
        """serve runs without an active REPL project; the SPA picks one."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path)))
        assert "No active project" not in capsys.readouterr().out

    def test_banned_host_prints_error(self, capsys, tmp_path) -> None:
        WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path), host="0.0.0.0"))
        assert "all interfaces" in capsys.readouterr().out

    def test_missing_ui_dir_prints_error(self, capsys, tmp_path) -> None:
        WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path)))
        assert "UI directory not found" in capsys.readouterr().out

    @patch("uvicorn.run")
    @patch("infrastructure.web_ui.runner.WebUiRunner._wait_for_port")
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_serve_starts_server_on_success(
        self,
        _mock_start_vite,
        mock_wait,
        mock_uvicorn_run,
        tmp_path,
        capsys,
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        app_mock = MagicMock()
        mock_factory = MagicMock(return_value=app_mock)
        mock_wait.return_value = True

        with patch("webbrowser.open") as mock_open:
            WebUiRunner(mock_factory).serve(**_serve_kwargs(str(tmp_path)))

        call_kwargs = mock_uvicorn_run.call_args
        assert call_kwargs.kwargs["host"] == "127.0.0.1"
        assert call_kwargs.kwargs["port"] == 8080
        assert call_kwargs.kwargs["ssl_certfile"]
        assert call_kwargs.kwargs["ssl_keyfile"]
        assert call_kwargs.kwargs["timeout_graceful_shutdown"] == 3
        out = capsys.readouterr().out
        assert "running at" in out
        opened_url = mock_open.call_args.args[0]
        assert opened_url.startswith("https://127.0.0.1:3000/?token=")
        assert opened_url.endswith("&fresh=1")

    @patch("uvicorn.run", side_effect=OSError("address already in use"))
    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_serve_prints_error_if_api_server_fails(
        self,
        _mock_start_vite,
        _mock_wait,
        _mock_uvicorn_run,
        tmp_path,
        capsys,
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path)))
        out = capsys.readouterr().out
        assert "already in use" in out or "failed to start" in out

    @patch("uvicorn.run")
    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_serve_blocks_on_main_thread(
        self,
        _mock_start_vite,
        _mock_wait,
        mock_uvicorn_run,
        tmp_path,
    ) -> None:
        """serve calls uvicorn.run directly; no daemon thread for the server."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path)))
        mock_uvicorn_run.assert_called_once()

    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    @patch("uvicorn.run", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_stops_cleanly(
        self,
        _mock_uvicorn_run,
        _mock_start_vite,
        _mock_wait,
        tmp_path,
    ) -> None:
        """KeyboardInterrupt is caught; serve() returns normally."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        runner = WebUiRunner(MagicMock())
        runner.serve(**_serve_kwargs(str(tmp_path)))

    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.subprocess.Popen")
    @patch("infrastructure.web_ui.runner.atexit.register")
    @patch("uvicorn.run")
    def test_vite_started_in_own_session(
        self,
        _mock_uvicorn_run,
        _mock_atexit,
        mock_popen,
        _mock_wait,
        tmp_path,
    ) -> None:
        """Vite subprocess is started with start_new_session=True."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        mock_popen.return_value = MagicMock()
        WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path)))
        _, call_kwargs = mock_popen.call_args
        assert call_kwargs.get("start_new_session") is True

    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.subprocess.Popen")
    @patch("infrastructure.web_ui.runner.atexit.register")
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
        runner = WebUiRunner(MagicMock())
        runner.serve(**_serve_kwargs(str(tmp_path)))
        mock_atexit.assert_called_once_with(runner._stop_vite)

    @patch("uvicorn.run")
    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_factory_receives_configured_host(
        self,
        _mock_start_vite,
        _mock_wait,
        _mock_uvicorn_run,
        tmp_path,
    ) -> None:
        """The app factory receives host so middleware can allowlist it."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        mock_factory = MagicMock()
        WebUiRunner(mock_factory).serve(
            **_serve_kwargs(str(tmp_path), host="10.1.20.101")
        )
        _, kwargs = mock_factory.call_args
        assert kwargs["host"] == "10.1.20.101"

    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_serve_prints_runtime_banner(
        self,
        _mock_start_vite,
        _mock_wait,
        tmp_path,
        capsys,
    ) -> None:
        """Banner prints before uvicorn.run is invoked."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        printed_before_run: list[str] = []

        def capture_run(*args: object, **kwargs: object) -> None:
            printed_before_run.append(capsys.readouterr().out)

        with patch("uvicorn.run", side_effect=capture_run):
            WebUiRunner(MagicMock()).serve(**_serve_kwargs(str(tmp_path)))

        assert printed_before_run, "uvicorn.run was not called"
        assert "Press Ctrl+C" in printed_before_run[0]


class TestMonitorVite:
    def test_prints_warning_when_vite_exits(self, capsys, tmp_path) -> None:
        proc = MagicMock()
        proc.poll.return_value = 1
        runner = WebUiRunner(MagicMock())
        runner._vite_proc = proc

        log_path = tmp_path / "vite.log"
        runner._monitor_vite(log_path)

        out = capsys.readouterr().out
        assert "exited (code 1)" in out
        assert str(log_path) in out

    def test_loops_until_exit(self, tmp_path) -> None:
        proc = MagicMock()
        proc.poll.side_effect = [None, None, 0]
        runner = WebUiRunner(MagicMock())
        runner._vite_proc = proc

        with patch("infrastructure.web_ui.runner.time.sleep") as mock_sleep:
            runner._monitor_vite(tmp_path / "vite.log")

        assert mock_sleep.call_count == 2

    def test_exits_silently_when_proc_cleared(self) -> None:
        runner = WebUiRunner(MagicMock())
        runner._vite_proc = None
        runner._monitor_vite(Path("/unused"))

    def test_silent_when_shutting_down(self, capsys) -> None:
        """Monitor does not print when _shutting_down is True."""
        proc = MagicMock()
        proc.poll.return_value = -2
        runner = WebUiRunner(MagicMock())
        runner._vite_proc = proc
        runner._shutting_down = True

        runner._monitor_vite(Path("/unused"))

        assert capsys.readouterr().out == ""


class TestStopVite:
    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_kills_process_group(self, mock_killpg) -> None:
        """_stop_vite sends SIGTERM to the process group, not just the process."""
        proc = MagicMock()
        proc.pid = 12345
        runner = WebUiRunner(MagicMock())
        runner._vite_proc = proc

        runner._stop_vite()

        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)
        proc.wait.assert_called_once_with(timeout=5)
        assert runner._vite_proc is None

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_sigkill_fallback_on_timeout(self, mock_killpg) -> None:
        """Falls back to SIGKILL when SIGTERM + wait times out."""
        proc = MagicMock()
        proc.pid = 12345
        proc.wait.side_effect = subprocess.TimeoutExpired("npm", 5)
        runner = WebUiRunner(MagicMock())
        runner._vite_proc = proc

        runner._stop_vite()

        assert mock_killpg.call_count == 2
        mock_killpg.assert_any_call(12345, signal.SIGTERM)
        mock_killpg.assert_any_call(12345, signal.SIGKILL)

    def test_noop_when_no_proc(self) -> None:
        """_stop_vite does nothing when _vite_proc is None."""
        runner = WebUiRunner(MagicMock())
        runner._stop_vite()


class TestKillpgSafe:
    """Verify the PID guard rejects invalid values before signaling."""

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_refuses_mock_pid(self, mock_killpg) -> None:
        WebUiRunner._killpg_safe(MagicMock(), signal.SIGTERM)
        mock_killpg.assert_not_called()

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_refuses_pid_zero(self, mock_killpg) -> None:
        WebUiRunner._killpg_safe(0, signal.SIGTERM)
        mock_killpg.assert_not_called()

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_refuses_pid_one(self, mock_killpg) -> None:
        WebUiRunner._killpg_safe(1, signal.SIGTERM)
        mock_killpg.assert_not_called()

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_refuses_negative_pid(self, mock_killpg) -> None:
        WebUiRunner._killpg_safe(-1, signal.SIGTERM)
        mock_killpg.assert_not_called()

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_refuses_bool(self, mock_killpg) -> None:
        WebUiRunner._killpg_safe(True, signal.SIGTERM)
        mock_killpg.assert_not_called()

    @patch("infrastructure.web_ui.runner.os.killpg")
    def test_accepts_valid_pid(self, mock_killpg) -> None:
        WebUiRunner._killpg_safe(12345, signal.SIGTERM)
        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)


class TestWriteEnvLocal:
    _CERT = Path("/fake/cert.pem")
    _KEY = Path("/fake/key.pem")

    def test_writes_expected_content(self, tmp_path) -> None:
        WebUiRunner._write_env_local(
            tmp_path, "127.0.0.1", 8080, 3000, self._CERT, self._KEY
        )
        content = (tmp_path / ".env.local").read_text()
        assert "TALLY_HOST=127.0.0.1" in content
        assert "TALLY_VITE_PORT=3000" in content
        assert "VITE_API_BASE_URL=https://127.0.0.1:8080" in content
        assert "TALLY_TLS_CERT=/fake/cert.pem" in content
        assert "TALLY_TLS_KEY=/fake/key.pem" in content

    def test_atomic_write_no_tmp_leftover(self, tmp_path) -> None:
        WebUiRunner._write_env_local(
            tmp_path, "127.0.0.1", 8080, 3000, self._CERT, self._KEY
        )
        assert (tmp_path / ".env.local").exists()
        assert not (tmp_path / ".env.local.tmp").exists()

    def test_overwrite_replaces_previous(self, tmp_path) -> None:
        WebUiRunner._write_env_local(
            tmp_path, "127.0.0.1", 8080, 3000, self._CERT, self._KEY
        )
        WebUiRunner._write_env_local(
            tmp_path, "localhost", 9090, 5173, self._CERT, self._KEY
        )
        content = (tmp_path / ".env.local").read_text()
        assert "TALLY_HOST=localhost" in content
        assert "TALLY_VITE_PORT=5173" in content
        assert "VITE_API_BASE_URL=https://localhost:9090" in content
        assert "127.0.0.1" not in content
