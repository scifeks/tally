"""Unit tests for application.config.mcp_defaults.load_mcp_defaults."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.config.mcp_defaults import load_mcp_defaults


@pytest.mark.unit
class TestLoadMcpDefaults:
    """Tests for load_mcp_defaults()."""

    _PATCH_TARGET = "application.config.mcp_defaults.ConfigManager"

    def test_file_not_found_returns_defaults(self) -> None:
        with patch(self._PATCH_TARGET, side_effect=FileNotFoundError):
            result = load_mcp_defaults("/some/root")
        assert result == (10, 30, 300)

    def test_success_path_returns_custom_values(self) -> None:
        mock_cfg = MagicMock()
        mock_cfg.mcp_batch_size = 20
        mock_cfg.mcp_batch_timeout_seconds = 60
        mock_cfg.mcp_session_timeout_seconds = 600

        mock_manager = MagicMock()
        mock_manager.global_config = mock_cfg

        with patch(self._PATCH_TARGET, return_value=mock_manager):
            result = load_mcp_defaults("/some/root")

        assert result == (20, 60, 600)

    def test_success_path_returns_default_values(self) -> None:
        mock_cfg = MagicMock()
        mock_cfg.mcp_batch_size = 10
        mock_cfg.mcp_batch_timeout_seconds = 30
        mock_cfg.mcp_session_timeout_seconds = 300

        mock_manager = MagicMock()
        mock_manager.global_config = mock_cfg

        with patch(self._PATCH_TARGET, return_value=mock_manager):
            result = load_mcp_defaults("/some/root")

        assert result == (10, 30, 300)
