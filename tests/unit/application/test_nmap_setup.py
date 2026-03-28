"""Unit tests for nmap_setup (application.setup.nmap_setup)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.setup.nmap_setup import (
    _interview_hosts,
    _prompt,
    interview_nmap_config,
)
from core.config.schemas.nmap_hosts_config import NmapHostsConfig
from core.config.schemas.nmap_profile import NmapProfile


class TestInterviewNmapConfig:
    # ------------------------------------------------------------------
    # _prompt
    # ------------------------------------------------------------------

    def test_prompt_returns_stripped_input(self) -> None:
        with patch("builtins.input", return_value="  myvalue  "):
            result = _prompt("Enter name")
        assert result == "myvalue"

    def test_prompt_returns_default_on_empty(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _prompt("Enter name", default="fallback")
        assert result == "fallback"

    def test_prompt_returns_empty_string_when_no_default(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _prompt("Enter name")
        assert result == ""

    # ------------------------------------------------------------------
    # _interview_hosts
    # ------------------------------------------------------------------

    def test_interview_hosts_valid_input(self) -> None:
        with (
            patch("builtins.input", return_value="192.168.1.1, 10.0.0.0/24"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
        ):
            result = _interview_hosts("Hosts")
        assert result == ["192.168.1.1", "10.0.0.0/24"]

    def test_interview_hosts_empty_input(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_hosts("Hosts")
        assert result == []

    def test_interview_hosts_invalid_then_valid(self) -> None:
        with (
            patch("builtins.input", side_effect=["bad-host", "192.168.1.1"]),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                side_effect=[False, True],
            ),
            patch("builtins.print"),
        ):
            result = _interview_hosts("Hosts")
        assert result == ["192.168.1.1"]

    # ------------------------------------------------------------------
    # interview_nmap_config — add mode
    # ------------------------------------------------------------------

    def test_add_mode_user_declines(self) -> None:
        mock_cm_instance = MagicMock()
        mock_cm_class = MagicMock(return_value=mock_cm_instance)

        with (
            patch("builtins.input", side_effect=["N"]),
            patch("builtins.print"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
            patch("core.config.manager.ConfigManager", mock_cm_class),
        ):
            interview_nmap_config("proj", "/base")

        mock_cm_instance.save_nmap_hosts.assert_not_called()

    def test_add_mode_one_scan_no_exclusions(self) -> None:
        mock_cm_instance = MagicMock()
        mock_cm_class = MagicMock(return_value=mock_cm_instance)

        inputs = ["y", "web-scan", "192.168.1.1", "-sV", "N", "N"]

        with (
            patch("builtins.input", side_effect=inputs),
            patch("builtins.print"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
            patch("core.config.manager.ConfigManager", mock_cm_class),
        ):
            interview_nmap_config("proj", "/base")

        mock_cm_instance.save_nmap_hosts.assert_called_once()
        args = mock_cm_instance.save_nmap_hosts.call_args[0]
        assert args[0] == "proj"
        profiles: dict[str, NmapProfile] = args[1]
        assert "web-scan" in profiles
        assert profiles["web-scan"].hosts == ["192.168.1.1"]
        assert profiles["web-scan"].nmap_args == "-sV"
        assert args[2] == []

    def test_add_mode_one_scan_with_exclusions(self) -> None:
        mock_cm_instance = MagicMock()
        mock_cm_class = MagicMock(return_value=mock_cm_instance)

        inputs = ["y", "web-scan", "192.168.1.1", "-sV", "N", "y", "10.0.0.0/8"]

        with (
            patch("builtins.input", side_effect=inputs),
            patch("builtins.print"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
            patch("core.config.manager.ConfigManager", mock_cm_class),
        ):
            interview_nmap_config("proj", "/base")

        mock_cm_instance.save_nmap_hosts.assert_called_once()
        args = mock_cm_instance.save_nmap_hosts.call_args[0]
        assert args[2] == ["10.0.0.0/8"]

    # ------------------------------------------------------------------
    # interview_nmap_config — edit mode
    # ------------------------------------------------------------------

    def test_edit_mode_keep_scan_keep_exclusions(self) -> None:
        existing = NmapHostsConfig(
            profiles={
                "old-scan": NmapProfile(hosts=["10.0.0.1"], nmap_args="-sV -sC -O")
            },
            excluded_networks=["172.16.0.0/12"],
        )
        mock_cm_instance = MagicMock()
        mock_cm_class = MagicMock(return_value=mock_cm_instance)

        inputs = ["", "", "", "", "", ""]

        with (
            patch("builtins.input", side_effect=inputs),
            patch("builtins.print"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
            patch("core.config.manager.ConfigManager", mock_cm_class),
        ):
            interview_nmap_config("proj", "/base", existing=existing)

        mock_cm_instance.save_nmap_hosts.assert_called_once()
        args = mock_cm_instance.save_nmap_hosts.call_args[0]
        profiles: dict[str, NmapProfile] = args[1]
        assert "old-scan" in profiles
        assert args[2] == ["172.16.0.0/12"]

    def test_edit_mode_delete_scan(self) -> None:
        existing = NmapHostsConfig(
            profiles={
                "old-scan": NmapProfile(hosts=["10.0.0.1"], nmap_args="-sV -sC -O")
            },
            excluded_networks=[],
        )
        mock_cm_instance = MagicMock()
        mock_cm_class = MagicMock(return_value=mock_cm_instance)

        inputs = ["", "", "n", "", ""]

        with (
            patch("builtins.input", side_effect=inputs),
            patch("builtins.print"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
            patch("core.config.manager.ConfigManager", mock_cm_class),
        ):
            interview_nmap_config("proj", "/base", existing=existing)

        mock_cm_instance.save_nmap_hosts.assert_called_once()
        args = mock_cm_instance.save_nmap_hosts.call_args[0]
        assert args[1] == {}
        assert args[2] == []

    def test_edit_mode_add_new_scan(self) -> None:
        existing = NmapHostsConfig(
            profiles={
                "old-scan": NmapProfile(hosts=["10.0.0.1"], nmap_args="-sV -sC -O")
            },
            excluded_networks=[],
        )
        mock_cm_instance = MagicMock()
        mock_cm_class = MagicMock(return_value=mock_cm_instance)

        inputs = ["", "", "", "y", "new-scan", "10.0.0.2", "", "", ""]

        with (
            patch("builtins.input", side_effect=inputs),
            patch("builtins.print"),
            patch(
                "application.setup.nmap_setup._is_valid_host",
                return_value=True,
            ),
            patch("core.config.manager.ConfigManager", mock_cm_class),
        ):
            interview_nmap_config("proj", "/base", existing=existing)

        mock_cm_instance.save_nmap_hosts.assert_called_once()
        args = mock_cm_instance.save_nmap_hosts.call_args[0]
        profiles: dict[str, NmapProfile] = args[1]
        assert "old-scan" in profiles
        assert "new-scan" in profiles
        assert profiles["new-scan"].hosts == ["10.0.0.2"]
        assert args[2] == []
