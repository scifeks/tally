"""Unit tests for vuln-data REPL commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.repl.commands.vuln_data_commands import (
    VulnDataCommands,
)


def _make_commands() -> tuple[VulnDataCommands, MagicMock]:
    repl = MagicMock()
    repl.base_path = "/tmp/test"
    cmds = VulnDataCommands(repl)
    return cmds, repl


_FACTORY_PATH = (
    "application.repl.commands.vuln_data_commands.get_vulnerability_data_service"
)


class TestVulnDataCommands:
    def test_status_no_data(self) -> None:
        cmds, repl = _make_commands()
        with patch(_FACTORY_PATH) as mock_factory:
            svc = MagicMock()
            svc.is_loaded.return_value = False
            mock_factory.return_value = svc
            cmds.cmd_vuln_data("vuln-data", ["status"])

        repl.console.print.assert_called()

    def test_status_with_data(self) -> None:
        cmds, repl = _make_commands()
        with patch(_FACTORY_PATH) as mock_factory:
            svc = MagicMock()
            svc.is_loaded.return_value = True
            svc.counts.return_value = (500, 200000)
            mock_factory.return_value = svc
            cmds.cmd_vuln_data("vuln-data", ["status"])

        svc.counts.assert_called_once()

    def test_update_calls_service(self) -> None:
        cmds, repl = _make_commands()
        with patch(_FACTORY_PATH) as mock_factory:
            svc = MagicMock()
            svc.update.return_value = (500, 200000)
            mock_factory.return_value = svc
            cmds.cmd_vuln_data("vuln-data", ["update"])

        svc.update.assert_called_once()

    def test_update_handles_error(self) -> None:
        cmds, repl = _make_commands()
        with patch(_FACTORY_PATH) as mock_factory:
            svc = MagicMock()
            svc.update.side_effect = Exception("network error")
            mock_factory.return_value = svc
            cmds.cmd_vuln_data("vuln-data", ["update"])

        assert any(
            "failed" in str(c).lower() for c in repl.console.print.call_args_list
        )

    def test_unknown_subcommand_prints_usage(self) -> None:
        cmds, repl = _make_commands()
        cmds.cmd_vuln_data("vuln-data", ["bogus"])
        repl.console.print.assert_called()

    def test_no_args_defaults_to_status(self) -> None:
        cmds, repl = _make_commands()
        with patch(_FACTORY_PATH) as mock_factory:
            svc = MagicMock()
            svc.is_loaded.return_value = False
            mock_factory.return_value = svc
            cmds.cmd_vuln_data("vuln-data", [])

        svc.is_loaded.assert_called()
