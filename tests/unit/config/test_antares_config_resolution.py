"""Tests for Antares inference config resolution."""

from __future__ import annotations

import pytest

from core.config.schemas.global_config import GlobalConfig
from infrastructure.llm.antares_config_resolver import (
    resolve_antares_config,
)


def _build_config(data: dict) -> GlobalConfig:
    return GlobalConfig(**data)


def _base(overrides: dict | None = None) -> dict:
    base = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "gemma4:latest",
        },
        "chat_inference": {"provider": "ollama"},
    }
    if overrides:
        base.update(overrides)
    return base


class TestAntaresConfigResolution:
    def test_explicit_model_used(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {
                        "provider": "ollama",
                        "model": "granite3-dense:2b",
                    },
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.model == "granite3-dense:2b"
        assert resolved.needs_shim is True
        assert resolved.ollama_base_url == "http://localhost:11434"

    def test_falls_back_to_chat_model(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                    "chat_inference": {
                        "provider": "ollama",
                        "model": "chat-specific-model",
                    },
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.model == "chat-specific-model"

    def test_falls_back_to_chat_provider_default(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.model == "gemma4:latest"

    def test_falls_back_to_triage_model(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                    "chat_inference": {"provider": "claude"},
                    "claude": {"model": "claude-opus-4-6", "api_key": "test"},
                    "triage_inference": {
                        "provider": "ollama",
                        "model": "qwen3:14b",
                    },
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.model == "qwen3:14b"

    def test_llama_cpp_no_shim(self) -> None:
        cfg = _build_config(
            {
                "llama_cpp": {
                    "base_url": "http://localhost:8080",
                    "model": "granite",
                },
                "antares_inference": {
                    "provider": "llama_cpp",
                },
            }
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.needs_shim is False
        assert resolved.ollama_base_url is None
        assert "8080" in resolved.endpoint_url

    def test_direct_base_url(self) -> None:
        cfg = _build_config(
            {
                "antares_inference": {
                    "provider": "vllm",
                    "base_url": "http://gpu-server:8000",
                    "model": "granite3-dense:2b",
                },
            }
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.endpoint_url == "http://gpu-server:8000"
        assert resolved.needs_shim is False

    def test_no_antares_config_raises(self) -> None:
        cfg = _build_config(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "x",
                }
            }
        )
        with pytest.raises(ValueError, match="antares_inference"):
            resolve_antares_config(cfg)

    def test_timeout_defaults_to_300(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.timeout_seconds == 300

    def test_timeout_override(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {
                        "provider": "ollama",
                        "timeout_seconds": 600,
                    },
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.timeout_seconds == 600

    def test_resolved_config_is_frozen(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        with pytest.raises(AttributeError, match="cannot assign to field"):
            resolved.model = "different"  # type: ignore[misc]

    def test_missing_model_raises(self) -> None:
        cfg = _build_config(
            {
                "antares_inference": {"provider": "ollama"},
            }
        )
        with pytest.raises(ValueError, match="Could not resolve model"):
            resolve_antares_config(cfg)

    def test_missing_ollama_base_url_raises(self) -> None:
        cfg = _build_config(
            {
                "antares_inference": {
                    "provider": "ollama",
                    "model": "test",
                },
            }
        )
        with pytest.raises(ValueError, match="ollama.base_url not configured"):
            resolve_antares_config(cfg)

    def test_missing_llama_cpp_base_url_raises(self) -> None:
        cfg = _build_config(
            {
                "antares_inference": {
                    "provider": "llama_cpp",
                    "model": "test",
                },
            }
        )
        with pytest.raises(ValueError, match="base_url not configured"):
            resolve_antares_config(cfg)

    def test_vllm_without_base_url_raises(self) -> None:
        cfg = _build_config(
            {
                "antares_inference": {
                    "provider": "vllm",
                    "model": "test",
                },
            }
        )
        with pytest.raises(ValueError, match="requires base_url in antares_inference"):
            resolve_antares_config(cfg)

    def test_llama_cpp_override_base_url_used(self) -> None:
        cfg = _build_config(
            {
                "llama_cpp": {
                    "base_url": "http://localhost:8080",
                    "model": "default-model",
                },
                "antares_inference": {
                    "provider": "llama_cpp",
                    "base_url": "http://override:8080",
                    "model": "test",
                },
            }
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.endpoint_url == "http://override:8080"

    def test_chat_model_override_preferred(self) -> None:
        cfg = _build_config(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "base-model",
                },
                "chat_inference": {
                    "provider": "ollama",
                    "model": "chat-override",
                },
                "antares_inference": {"provider": "ollama"},
            }
        )
        resolved = resolve_antares_config(cfg)
        # Should use chat_inference model, not base ollama model
        assert resolved.model == "chat-override"

    def test_triage_used_only_if_chat_not_ollama(self) -> None:
        cfg = _build_config(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "base-model",
                },
                "chat_inference": {
                    "provider": "claude",
                    "model": "claude-opus",
                },
                "claude": {"model": "claude-opus", "api_key": "test"},
                "triage_inference": {
                    "provider": "ollama",
                    "model": "triage-model",
                },
                "antares_inference": {"provider": "ollama"},
            }
        )
        resolved = resolve_antares_config(cfg)
        # Should skip chat (not ollama) and use triage
        assert resolved.model == "triage-model"

    def test_non_ollama_provider_ignores_ollama_fallback(self) -> None:
        cfg = _build_config(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "ollama-model",
                },
                "chat_inference": {
                    "provider": "ollama",
                    "model": "chat-ollama-model",
                },
                "antares_inference": {
                    "provider": "vllm",
                    "base_url": "http://gpu-server:8000",
                    # No model specified: should error, not fall back to ollama
                },
            }
        )
        with pytest.raises(ValueError, match="Could not resolve model"):
            resolve_antares_config(cfg)

    def test_sweep_config_provides_max_cwes_and_workers(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                    "antares_sweep_config": {
                        "max_cwes": 20,
                        "workers": 6,
                    },
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.max_cwes == 20
        assert resolved.workers == 6

    def test_sweep_config_defaults_to_none(self) -> None:
        cfg = _build_config(
            _base(
                {
                    "antares_inference": {"provider": "ollama"},
                }
            )
        )
        resolved = resolve_antares_config(cfg)
        assert resolved.max_cwes is None
        assert resolved.workers is None
