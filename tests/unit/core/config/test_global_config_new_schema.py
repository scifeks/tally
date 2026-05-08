"""Unit tests for new GlobalConfig schema with feature configs."""

from __future__ import annotations

from core.config.schemas import (
    ClaudeConfig,
    FeatureInferenceConfig,
    GlobalConfig,
    LocalInferenceConfig,
)


class TestGlobalConfigNewSchema:
    def test_minimal_config(self) -> None:
        config = GlobalConfig(
            ollama=LocalInferenceConfig(
                base_url="http://localhost:11434",
                model="qwen3:14b",
            ),
            chat_inference=FeatureInferenceConfig(provider="ollama"),
            enrichment_inference=FeatureInferenceConfig(provider="ollama"),
            report_inference=FeatureInferenceConfig(provider="ollama"),
            embedding_inference=FeatureInferenceConfig(provider="ollama"),
        )
        assert config.ollama is not None
        assert config.ollama.model == "qwen3:14b"
        assert config.chat_inference is not None
        assert config.chat_inference.provider == "ollama"

    def test_multiple_providers(self) -> None:
        config = GlobalConfig(
            ollama=LocalInferenceConfig(
                base_url="http://localhost:11434",
                model="qwen3:14b",
            ),
            llama_cpp=LocalInferenceConfig(
                base_url="http://localhost:8000",
                model="llama2",
            ),
            claude=ClaudeConfig(
                api_key="sk-test",
                model="claude-opus-4-5",
                max_tokens=2048,
            ),
            chat_inference=FeatureInferenceConfig(provider="claude"),
            enrichment_inference=FeatureInferenceConfig(provider="ollama"),
            report_inference=FeatureInferenceConfig(
                provider="llama_cpp",
                timeout_seconds=180,
            ),
            embedding_inference=FeatureInferenceConfig(provider="ollama"),
        )
        assert config.claude is not None
        assert config.llama_cpp is not None
        assert config.chat_inference is not None
        assert config.chat_inference.provider == "claude"
        assert config.report_inference is not None
        assert config.report_inference.timeout_seconds == 180

    def test_noir_inference_optional(self) -> None:
        config = GlobalConfig()
        assert config.noir_inference is None

    def test_noir_inference_configured(self) -> None:
        config = GlobalConfig(
            ollama=LocalInferenceConfig(model="qwen3:14b"),
            noir_inference=FeatureInferenceConfig(provider="ollama"),
        )
        assert config.noir_inference is not None
        assert config.noir_inference.provider == "ollama"

    def test_preserves_non_inference_fields(self) -> None:
        config = GlobalConfig(
            projects_dir="./custom_projects",
            report_retention_count=5,
        )
        assert config.projects_dir == "./custom_projects"
        assert config.report_retention_count == 5

    def test_old_fields_silently_ignored(self) -> None:
        data = {
            "chat_llm_provider": "ollama",
            "ollama": {"model": "qwen3:14b"},
            "chat_inference": {"provider": "ollama"},
        }
        config = GlobalConfig(**data)
        assert not hasattr(config, "chat_llm_provider")

    def test_all_feature_configs_none_by_default(self) -> None:
        config = GlobalConfig()
        assert config.chat_inference is None
        assert config.enrichment_inference is None
        assert config.report_inference is None
        assert config.embedding_inference is None
        assert config.noir_inference is None

    def test_all_provider_configs_none_by_default(self) -> None:
        config = GlobalConfig()
        assert config.ollama is None
        assert config.llama_cpp is None
        assert config.claude is None
