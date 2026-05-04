"""Tests for UiCommands (the REPL-side `ui` handler)."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.ports.web_ui_runner import WebUiRunnerPort
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
    base_path: str = "/tmp/tally_test",
    host: str = "127.0.0.1",
) -> MagicMock:
    repl = MagicMock()
    repl.base_path = base_path
    repl.config.global_config = _make_global_config(host=host)
    return repl


class TestServeCommand:
    def test_cmd_serve_invokes_runner_with_config_values(self) -> None:
        runner = MagicMock(spec=WebUiRunnerPort)
        repl = _make_repl_mock(base_path="/tmp/tally_test", host="127.0.0.1")
        UiCommands(repl, web_ui_runner=runner).cmd_serve([])
        runner.serve.assert_called_once_with(
            base_path="/tmp/tally_test",
            host="127.0.0.1",
            api_port=8080,
            vite_port=3000,
            allowed_origins=["http://127.0.0.1:3000"],
            project_registry=repl.project_registry,
            tool_registry=repl.tool_registry,
        )

    def test_stop_flag_no_longer_recognized(self) -> None:
        """Passing --stop no longer short-circuits; serve proceeds normally."""
        runner = MagicMock(spec=WebUiRunnerPort)
        UiCommands(_make_repl_mock(), web_ui_runner=runner).cmd_serve(["--stop"])
        runner.serve.assert_called_once()

    def test_ui_stop_method_removed(self) -> None:
        assert not hasattr(UiCommands, "_cmd_stop")

    def test_help_text_drops_stop(self, capsys) -> None:
        UiCommands(_make_repl_mock(), web_ui_runner=MagicMock())._show_help()
        assert "--stop" not in capsys.readouterr().out

    def test_cmd_serve_help_includes_ctrl_c_message(self) -> None:
        assert "Press Ctrl+C to stop the server." in (
            UiCommands.cmd_serve.__doc__ or ""
        )


class TestUiDispatch:
    def test_cmd_ui_no_args_shows_help(self, capsys) -> None:
        runner = MagicMock(spec=WebUiRunnerPort)
        UiCommands(_make_repl_mock(), web_ui_runner=runner).cmd_ui("ui", [])
        assert "ui serve" in capsys.readouterr().out
        runner.serve.assert_not_called()

    def test_cmd_ui_serve_dispatches_to_serve(self) -> None:
        runner = MagicMock(spec=WebUiRunnerPort)
        UiCommands(_make_repl_mock(), web_ui_runner=runner).cmd_ui("ui", ["serve"])
        runner.serve.assert_called_once()

    def test_cmd_ui_unknown_subcommand_shows_help(self, capsys) -> None:
        runner = MagicMock(spec=WebUiRunnerPort)
        UiCommands(_make_repl_mock(), web_ui_runner=runner).cmd_ui("ui", ["banana"])
        out = capsys.readouterr().out
        assert "Unknown subcommand: banana" in out
        assert "ui serve" in out
        runner.serve.assert_not_called()
