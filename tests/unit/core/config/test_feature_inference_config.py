"""Unit tests for FeatureInferenceConfig schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.schemas import FeatureInferenceConfig


class TestFeatureInferenceConfig:
    def test_valid_config_with_provider_only(self) -> None:
        config = FeatureInferenceConfig(provider="ollama")
        assert config.provider == "ollama"
        assert config.model is None
        assert config.timeout_seconds is None
        assert config.num_ctx is None
        assert config.max_tokens is None

    def test_config_with_all_overrides(self) -> None:
        config = FeatureInferenceConfig(
            provider="ollama",
            model="qwen2.5:32b",
            timeout_seconds=120,
            num_ctx=4096,
            max_tokens=2048,
        )
        assert config.provider == "ollama"
        assert config.model == "qwen2.5:32b"
        assert config.timeout_seconds == 120
        assert config.num_ctx == 4096
        assert config.max_tokens == 2048

    def test_provider_required(self) -> None:
        with pytest.raises(ValidationError):
            FeatureInferenceConfig.model_validate({"model": "qwen3:14b"})

    def test_partial_overrides(self) -> None:
        config = FeatureInferenceConfig(
            provider="llama_cpp",
            timeout_seconds=90,
        )
        assert config.provider == "llama_cpp"
        assert config.timeout_seconds == 90
        assert config.model is None
        assert config.num_ctx is None
        assert config.max_tokens is None

    def test_timeout_seconds_positive(self) -> None:
        with pytest.raises(ValidationError):
            FeatureInferenceConfig(
                provider="ollama",
                timeout_seconds=-1,
            )

    def test_num_ctx_positive_or_none(self) -> None:
        config = FeatureInferenceConfig(
            provider="ollama",
            num_ctx=8192,
        )
        assert config.num_ctx == 8192

        with pytest.raises(ValidationError):
            FeatureInferenceConfig(
                provider="ollama",
                num_ctx=-1,
            )

    def test_max_tokens_positive_or_none(self) -> None:
        config = FeatureInferenceConfig(
            provider="claude",
            max_tokens=1024,
        )
        assert config.max_tokens == 1024

        with pytest.raises(ValidationError):
            FeatureInferenceConfig(
                provider="claude",
                max_tokens=-1,
            )
