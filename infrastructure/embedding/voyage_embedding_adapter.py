"""Voyage AI embedding provider adapter."""

from __future__ import annotations

import logging
import os
from typing import Any

from voyageai.client import Client as VoyageClient

from application.ports.embedding_provider import (
    EmbeddingAdapterError,
    EmbeddingProvider,
)

logger = logging.getLogger(__name__)


class VoyageEmbeddingAdapter(EmbeddingProvider):
    """EmbeddingProvider backed by Voyage AI API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int = 60,
        debug: bool = False,
    ) -> None:
        self._resolved_key = os.environ.get("VOYAGE_API_KEY") or api_key or ""
        self._model = model
        self._timeout = timeout_seconds
        self._debug = debug
        self._client = VoyageClient(
            api_key=self._resolved_key or "not-set",
            max_retries=0,
        )

    def is_available(self) -> bool:
        """Return True if API key is configured."""
        return bool(self._resolved_key)

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Call Voyage AI embed endpoint and return the embedding vector."""
        if self._debug:
            logger.debug(
                "embed: model=%s text_len=%d",
                self._model,
                len(text),
            )
        try:
            result = self._client.embed(texts=[text], model=self._model)
            embedding = result.embeddings[0]
            return [float(x) for x in embedding]
        except Exception as exc:
            raise EmbeddingAdapterError(str(exc)) from exc
