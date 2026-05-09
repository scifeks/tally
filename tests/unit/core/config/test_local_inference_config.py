"""Unit tests for LocalInferenceConfig schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.schemas import LocalInferenceConfig


class TestLocalInferenceConfig:
    def test_valid_config(self) -> None:
        config = LocalInferenceConfig(
            base_url="http://localhost:11434",
            model="qwen3:14b",
            timeout_seconds=60,
            num_ctx=8192,
        )
        assert config.base_url == "http://localhost:11434"
        assert config.model == "qwen3:14b"
        assert config.timeout_seconds == 60
        assert config.num_ctx == 8192

    def test_default_base_url(self) -> None:
        config = LocalInferenceConfig(model="qwen3:14b")
        assert config.base_url == "http://localhost:11434"

    def test_default_timeout_seconds(self) -> None:
        config = LocalInferenceConfig(model="qwen3:14b")
        assert config.timeout_seconds == 60

    def test_num_ctx_optional(self) -> None:
        config = LocalInferenceConfig(
            base_url="http://localhost:11434",
            model="qwen3:14b",
            num_ctx=None,
        )
        assert config.num_ctx is None

    def test_base_url_must_start_with_http(self) -> None:
        with pytest.raises(ValidationError, match="http"):
            LocalInferenceConfig(
                base_url="localhost:11434",
                model="qwen3:14b",
            )

    def test_base_url_strips_trailing_slash(self) -> None:
        config = LocalInferenceConfig(
            base_url="http://localhost:11434/",
            model="qwen3:14b",
        )
        assert config.base_url == "http://localhost:11434"

    def test_https_base_url_accepted(self) -> None:
        config = LocalInferenceConfig(
            base_url="https://inference.example.com:8443",
            model="qwen3:14b",
        )
        assert config.base_url == "https://inference.example.com:8443"

    def test_model_required(self) -> None:
        with pytest.raises(ValidationError):
            LocalInferenceConfig.model_validate({"base_url": "http://localhost:11434"})
