"""BurpConfig schema validation."""

from __future__ import annotations

import pytest

from core.config.schemas.burp_config import BurpConfig
from core.config.schemas.global_config import GlobalConfig


class TestBurpConfig:
    def test_default_values(self) -> None:
        config = BurpConfig()
        assert config.base_url == "http://localhost:1337"
        assert config.api_key == ""

    def test_custom_values(self) -> None:
        config = BurpConfig(
            base_url="http://10.1.20.101:1337",
            api_key="secret",
        )
        assert config.base_url == "http://10.1.20.101:1337"
        assert config.api_key == "secret"

    def test_trailing_slash_stripped(self) -> None:
        config = BurpConfig(base_url="http://localhost:1337/")
        assert config.base_url == "http://localhost:1337"

    def test_invalid_url_scheme_rejected(self) -> None:
        with pytest.raises(ValueError, match="http:// or https://"):
            BurpConfig(base_url="ftp://localhost")

    def test_global_config_burp_defaults_to_none(self) -> None:
        config = GlobalConfig()
        assert config.burp is None

    def test_global_config_accepts_burp_dict(self) -> None:
        config = GlobalConfig.model_validate(
            {"burp": {"base_url": "http://10.0.0.1:1337"}}
        )
        assert config.burp is not None
        assert config.burp.base_url == "http://10.0.0.1:1337"
