"""Ollama embedding provider adapter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from application.ports.embedding_provider import EmbeddingProvider


class OllamaEmbeddingAdapter(EmbeddingProvider):
    """EmbeddingProvider backed by a local Ollama instance."""

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
        """Return True if Ollama responds at its /api/tags endpoint."""
        try:
            with urllib.request.urlopen(
                f"{self._base_url}/api/tags", timeout=5
            ) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        """POST to /api/embeddings and return the embedding vector."""
        payload = json.dumps({"model": self._model, "prompt": text}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["embedding"]
