"""Unit tests for get_llm_provider returning OllamaAdapter."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.llm.factory import get_llm_provider
from infrastructure.llm.ollama_adapter import OllamaAdapter

_OLLAMA_URL = "http://localhost:11434"


def _write_global_config(base_path: Path, overrides: dict | None = None) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "ollama": {
            "base_url": _OLLAMA_URL,
            "model": "qwen3:14b",
        },
        "chat_inference": {"provider": "ollama"},
        "enrichment_inference": {"provider": "ollama"},
        "report_inference": {"provider": "ollama"},
        "embedding_inference": {
            "provider": "ollama",
            "model": "nomic-embed-text:latest",
        },
    }
    if overrides:
        base.update(overrides)
    (config_dir / "global.json").write_text(json.dumps(base))


class TestGetLlmProviderReturnsOllama:
    def test_chat_role(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_enrichment_role(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("enrichment", tmp_path)
        assert isinstance(provider, OllamaAdapter)

    def test_report_role(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, OllamaAdapter)


class TestOllamaReportOverride:
    """report_inference can override the model independently."""

    def test_report_uses_overridden_model(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {
                "report_inference": {
                    "provider": "ollama",
                    "model": "qwen2.5:14b",
                },
            },
        )
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._model == "qwen2.5:14b"

    def test_report_uses_base_model_without_override(self, tmp_path: Path) -> None:
        _write_global_config(tmp_path)
        provider = get_llm_provider("report", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._model == "qwen3:14b"

    def test_enrichment_unaffected_by_report_override(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {
                "report_inference": {
                    "provider": "ollama",
                    "model": "qwen2.5:14b",
                },
            },
        )
        provider = get_llm_provider("enrichment", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._model == "qwen3:14b"

    def test_chat_unaffected_by_report_override(self, tmp_path: Path) -> None:
        _write_global_config(
            tmp_path,
            {
                "report_inference": {
                    "provider": "ollama",
                    "model": "qwen2.5:14b",
                },
            },
        )
        provider = get_llm_provider("chat", tmp_path)
        assert isinstance(provider, OllamaAdapter)
        assert provider._model == "qwen3:14b"
