"""Unit tests for VoyageEmbeddingAdapter.is_available()."""

from __future__ import annotations

import os
from unittest.mock import patch

from infrastructure.embedding.voyage_embedding_adapter import (
    VoyageEmbeddingAdapter,
)


class TestVoyageEmbeddingIsAvailable:
    def test_returns_true_when_api_key_provided(self) -> None:
        adapter = VoyageEmbeddingAdapter(
            api_key="pa-test-key",
            model="voyage-3",
        )
        assert adapter.is_available() is True

    def test_returns_true_when_api_key_from_env(self) -> None:
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "env-key"}):
            adapter = VoyageEmbeddingAdapter(api_key="", model="voyage-3")
            assert adapter.is_available() is True

    def test_returns_false_when_no_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOYAGE_API_KEY", None)
            adapter = VoyageEmbeddingAdapter(api_key="", model="voyage-3")
            assert adapter.is_available() is False

    def test_env_var_satisfies_availability(self) -> None:
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "env-key"}):
            adapter = VoyageEmbeddingAdapter(
                api_key="",
                model="voyage-3",
            )
        assert adapter.is_available() is True
