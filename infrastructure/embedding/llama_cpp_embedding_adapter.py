"""llama.cpp embedding provider adapter."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from typing import Any

import openai

from application.ports.embedding_provider import (
    EmbeddingAdapterError,
    EmbeddingProvider,
)

logger = logging.getLogger(__name__)


class LlamaCppEmbeddingAdapter(EmbeddingProvider):
    """EmbeddingProvider backed by a local llama.cpp server."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    def is_available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self._base_url}/health", timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        try:
            client = openai.OpenAI(
                base_url=f"{self._base_url}/v1",
                api_key="not-needed",
                timeout=self._timeout,
            )
            response = client.embeddings.create(
                input=text,
                model=self._model,
                **kwargs,
            )
            return response.data[0].embedding
        except Exception as exc:
            raise EmbeddingAdapterError(str(exc)) from exc
