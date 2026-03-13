"""Ollama LLM provider adapter."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

import ollama

from .base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaAdapter(LLMProvider):
    """LLMProvider backed by a local Ollama instance."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if Ollama responds at its /api/tags endpoint."""
        try:
            with urllib.request.urlopen(
                f"{self._base_url}/api/tags", timeout=5
            ) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call ollama.Client.chat and return the response content string."""
        client = ollama.Client(host=self._base_url)
        response = client.chat(
            model=self._model,
            messages=messages,
            options={**kwargs},
        )
        msg = response.message if hasattr(response, "message") else response["message"]
        content = msg.content if hasattr(msg, "content") else msg["content"]
        return content or ""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Delegate to chat() with a single user message."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)


# ---------------------------------------------------------------------------
# Module-level shims — preserve existing import paths in callers that
# previously imported these helpers directly from core.rag.engine.
# ---------------------------------------------------------------------------


def verify_ollama_available(base_url: str) -> bool:
    """Return True if Ollama is reachable at base_url."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def get_ollama_models(base_url: str) -> list[str]:
    """Return a list of model names available in Ollama."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return []
