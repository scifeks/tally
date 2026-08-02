"""Unit tests for GlobalConfig schema. Web UI fields and validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.schemas.global_config import GlobalConfig


class TestDefaults:
    def test_web_ui_host_default(self) -> None:
        cfg = GlobalConfig()
        assert cfg.web_ui_host == "127.0.0.1"

    def test_web_ui_port_default(self) -> None:
        cfg = GlobalConfig()
        assert cfg.web_ui_port == 8080

    def test_web_ui_vite_port_default(self) -> None:
        cfg = GlobalConfig()
        assert cfg.web_ui_vite_port == 3000

    def test_web_ui_allowed_origins_default_is_none(self) -> None:
        cfg = GlobalConfig()
        assert cfg.web_ui_allowed_origins is None

    def test_triage_agent_provider_default(self) -> None:
        cfg = GlobalConfig()
        assert cfg.triage_agent_provider == ""


class TestHostValidator:
    @pytest.mark.parametrize("bad_host", ["0.0.0.0", "::", ""])
    def test_banned_host_raises(self, bad_host: str) -> None:
        with pytest.raises(ValidationError):
            GlobalConfig(web_ui_host=bad_host)

    def test_localhost_string_accepted(self) -> None:
        cfg = GlobalConfig(web_ui_host="localhost")
        assert cfg.web_ui_host == "localhost"

    def test_custom_ip_accepted(self) -> None:
        cfg = GlobalConfig(web_ui_host="192.168.1.10")
        assert cfg.web_ui_host == "192.168.1.10"


class TestEffectiveAllowedOrigins:
    def test_derived_when_not_set(self) -> None:
        cfg = GlobalConfig(
            web_ui_host="127.0.0.1",
            web_ui_vite_port=3000,
        )
        assert cfg.effective_allowed_origins == ["https://127.0.0.1:3000"]

    def test_explicit_list_returned_when_set(self) -> None:
        origins = ["http://127.0.0.1:3000", "http://localhost:3000"]
        cfg = GlobalConfig(web_ui_allowed_origins=origins)
        assert cfg.effective_allowed_origins == origins

    def test_derived_uses_configured_host_and_port(self) -> None:
        cfg = GlobalConfig(web_ui_host="localhost", web_ui_vite_port=5173)
        assert cfg.effective_allowed_origins == ["https://localhost:5173"]

    def test_empty_explicit_list_falls_back_to_derived(self) -> None:
        cfg = GlobalConfig(
            web_ui_host="127.0.0.1",
            web_ui_vite_port=3000,
            web_ui_allowed_origins=[],
        )
        assert cfg.effective_allowed_origins == ["https://127.0.0.1:3000"]


class TestExtraFieldsIgnored:
    def test_unknown_key_silently_ignored(self) -> None:
        cfg = GlobalConfig.model_validate({"subprocess_stream_chunk_bytes": 268435456})
        assert not hasattr(cfg, "subprocess_stream_chunk_bytes")


class TestTriageAgentProvider:
    def test_empty_string_disables_triage(self) -> None:
        cfg = GlobalConfig(triage_agent_provider="")
        assert cfg.triage_agent_provider == ""

    def test_open_code_accepted(self) -> None:
        cfg = GlobalConfig(triage_agent_provider="open_code")
        assert cfg.triage_agent_provider == "open_code"

    def test_unknown_provider_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GlobalConfig.model_validate({"triage_agent_provider": "something_else"})


class TestChatSessionRetention:
    def test_default_is_twenty(self) -> None:
        assert GlobalConfig().chat_session_retention_count == 20

    def test_zero_disables_sweeping(self) -> None:
        assert (
            GlobalConfig(chat_session_retention_count=0).chat_session_retention_count
            == 0
        )

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GlobalConfig(chat_session_retention_count=-1)


class TestLocalInferenceConfigBaseUrlNormalization:
    def test_base_url_strips_trailing_slash(self) -> None:
        from core.config.schemas import LocalInferenceConfig

        config = LocalInferenceConfig(
            base_url="http://localhost:11434/",
            model="qwen3:14b",
        )
        assert config.base_url == "http://localhost:11434"
