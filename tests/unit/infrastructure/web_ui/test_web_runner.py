"""Tests for WebUiRunner (the WebUiRunnerPort adapter)."""

from __future__ import annotations

from typing import TypedDict
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.web_ui.runner import WebUiRunner


class _ServeKwargs(TypedDict):
    base_path: str
    host: str
    api_port: int
    vite_port: int
    allowed_origins: list[str]


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
            else [f"http://{host}:{vite_port}"]
        ),
    }


class TestServe:
    @patch("infrastructure.web_ui.runner.create_web_app")
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
        _mock_factory,
        tmp_path,
        capsys,
    ) -> None:
        """serve runs without an active REPL project; the SPA picks one."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))
        assert "No active project" not in capsys.readouterr().out

    def test_banned_host_prints_error(self, capsys, tmp_path) -> None:
        WebUiRunner().serve(**_serve_kwargs(str(tmp_path), host="0.0.0.0"))
        assert "all interfaces" in capsys.readouterr().out

    def test_missing_ui_dir_prints_error(self, capsys, tmp_path) -> None:
        WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))
        assert "UI directory not found" in capsys.readouterr().out

    @patch("infrastructure.web_ui.runner.create_web_app")
    @patch("uvicorn.run")
    @patch("infrastructure.web_ui.runner.WebUiRunner._wait_for_port")
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_serve_starts_server_on_success(
        self,
        _mock_start_vite,
        mock_wait,
        mock_uvicorn_run,
        mock_factory,
        tmp_path,
        capsys,
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        app_mock = MagicMock()
        mock_factory.return_value = app_mock
        mock_wait.return_value = True

        with patch("webbrowser.open") as mock_open:
            WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))

        mock_uvicorn_run.assert_called_once_with(
            app_mock, host="127.0.0.1", port=8080, log_level="warning"
        )
        out = capsys.readouterr().out
        assert "running at" in out
        # The browser URL must carry `&fresh=1` so the SPA clears any
        # persisted activeProjectId on each `ui serve` invocation.
        opened_url = mock_open.call_args.args[0]
        assert opened_url.startswith("http://127.0.0.1:3000/?token=")
        assert opened_url.endswith("&fresh=1")

    @patch("infrastructure.web_ui.runner.create_web_app")
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
        _mock_factory,
        tmp_path,
        capsys,
    ) -> None:
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))
        out = capsys.readouterr().out
        assert "already in use" in out or "failed to start" in out

    @patch("infrastructure.web_ui.runner.create_web_app")
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
        _mock_factory,
        tmp_path,
    ) -> None:
        """serve calls uvicorn.run directly; no daemon thread for the server."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))
        mock_uvicorn_run.assert_called_once()

    @patch("infrastructure.web_ui.runner.create_web_app")
    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    @patch("uvicorn.run", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_propagates(
        self,
        _mock_uvicorn_run,
        _mock_start_vite,
        _mock_wait,
        _mock_factory,
        tmp_path,
    ) -> None:
        """KeyboardInterrupt from uvicorn propagates to the caller."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        with pytest.raises(KeyboardInterrupt):
            WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))

    @patch("infrastructure.web_ui.runner.create_web_app")
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
        _mock_factory,
        tmp_path,
    ) -> None:
        """_start_vite registers atexit hook for Vite subprocess teardown."""
        ui_dir = tmp_path / "ui"
        ui_dir.mkdir()
        mock_popen.return_value = MagicMock()
        runner = WebUiRunner()
        runner.serve(**_serve_kwargs(str(tmp_path)))
        mock_atexit.assert_called_once_with(runner._stop_vite)

    @patch("infrastructure.web_ui.runner.create_web_app")
    @patch(
        "infrastructure.web_ui.runner.WebUiRunner._wait_for_port",
        return_value=False,
    )
    @patch("infrastructure.web_ui.runner.WebUiRunner._start_vite")
    def test_serve_prints_runtime_banner(
        self,
        _mock_start_vite,
        _mock_wait,
        _mock_factory,
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
            WebUiRunner().serve(**_serve_kwargs(str(tmp_path)))

        assert printed_before_run, "uvicorn.run was not called"
        assert "Press Ctrl+C" in printed_before_run[0]


class TestWriteEnvLocal:
    def test_writes_expected_content(self, tmp_path) -> None:
        WebUiRunner._write_env_local(tmp_path, "127.0.0.1", 8080, 3000)
        content = (tmp_path / ".env.local").read_text()
        assert "TALLY_HOST=127.0.0.1" in content
        assert "TALLY_VITE_PORT=3000" in content
        assert "VITE_API_BASE_URL=http://127.0.0.1:8080" in content

    def test_atomic_write_no_tmp_leftover(self, tmp_path) -> None:
        WebUiRunner._write_env_local(tmp_path, "127.0.0.1", 8080, 3000)
        assert (tmp_path / ".env.local").exists()
        assert not (tmp_path / ".env.local.tmp").exists()

    def test_overwrite_replaces_previous(self, tmp_path) -> None:
        WebUiRunner._write_env_local(tmp_path, "127.0.0.1", 8080, 3000)
        WebUiRunner._write_env_local(tmp_path, "localhost", 9090, 5173)
        content = (tmp_path / ".env.local").read_text()
        assert "TALLY_HOST=localhost" in content
        assert "TALLY_VITE_PORT=5173" in content
        assert "VITE_API_BASE_URL=http://localhost:9090" in content
        assert "127.0.0.1" not in content
