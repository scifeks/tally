"""Burp availability probe tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from core.config.schemas.burp_config import BurpConfig
from infrastructure.tools.burp.probe import (
    probe_burp_availability,
)

_CLIENT = "infrastructure.tools.burp.rest_client"


class TestBurpAvailabilityProbe:
    def test_returns_none_when_not_configured(self) -> None:
        assert probe_burp_availability(None) is None

    def test_returns_true_when_healthy(self) -> None:
        config = BurpConfig(base_url="http://localhost:1337")
        mock_resp = MagicMock(status_code=200)
        with patch(
            f"{_CLIENT}.httpx.get",
            return_value=mock_resp,
        ):
            assert probe_burp_availability(config) is True

    def test_returns_false_when_offline(self) -> None:
        config = BurpConfig(base_url="http://localhost:1337")
        with patch(
            f"{_CLIENT}.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = probe_burp_availability(config)
            assert result is False

    def test_returns_false_on_non_200(self) -> None:
        config = BurpConfig(base_url="http://localhost:1337")
        mock_resp = MagicMock(status_code=500)
        with patch(
            f"{_CLIENT}.httpx.get",
            return_value=mock_resp,
        ):
            result = probe_burp_availability(config)
            assert result is False
