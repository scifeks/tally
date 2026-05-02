"""Snapshot resolution branches inside ``make_context``.

The ``noir_provider`` field on ``GlobalConfig`` is a string naming
another field on the same model. ``make_context`` resolves the string
to a frozen ``NoirProviderSnapshot`` (or ``None``) so that wrappers
hold no reference to ``ConfigManager`` or ``GlobalConfig``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.tools.scan_types.execution import _build_tool_execution_config
from core.config.schemas import OllamaConfig
from core.config.schemas.global_config import GlobalConfig


def _make_config_manager(global_config: GlobalConfig) -> MagicMock:
    cm = MagicMock()
    cm.global_config = global_config
    return cm


class TestBuildToolExecutionConfig:
    def test_empty_provider_yields_none(self) -> None:
        gc = GlobalConfig.model_construct(noir_provider="")
        result = _build_tool_execution_config(_make_config_manager(gc))
        assert result.noir_provider is None

    def test_valid_provider_populates_snapshot(self) -> None:
        provider = OllamaConfig(
            base_url="http://10.0.0.1:11434",
            model="gemma3:27b",
            num_ctx=8192,
        )
        gc = GlobalConfig.model_construct(
            noir_provider="ollama_noir",
            ollama_noir=provider,
        )
        result = _build_tool_execution_config(_make_config_manager(gc))
        assert result.noir_provider is not None
        assert result.noir_provider.base_url == "http://10.0.0.1:11434"
        assert result.noir_provider.model == "gemma3:27b"
        assert result.noir_provider.num_ctx == 8192

    def test_unknown_provider_name_yields_none(self) -> None:
        gc = GlobalConfig.model_construct(noir_provider="nonexistent_provider")
        result = _build_tool_execution_config(_make_config_manager(gc))
        assert result.noir_provider is None

    def test_provider_without_base_url_yields_none(self) -> None:
        # ClaudeConfig has no base_url; the snapshot tolerates the misuse
        # by returning None rather than crashing the wrapper.
        gc = GlobalConfig.model_construct(noir_provider="claude")
        result = _build_tool_execution_config(_make_config_manager(gc))
        assert result.noir_provider is None
