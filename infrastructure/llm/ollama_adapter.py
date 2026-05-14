"""Ollama LLM provider adapter."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any

import ollama

from application.ports.llm_provider import LLMAdapterError, LLMProvider

logger = logging.getLogger(__name__)


class OllamaAdapter(LLMProvider):
    """LLMProvider backed by a local Ollama instance."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 60,
        num_ctx: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._num_ctx = num_ctx

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        """Return True if Ollama responds at its /api/tags endpoint."""
        try:
            with urllib.request.urlopen(
                f"{self._base_url}/api/tags", timeout=5
            ) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def _build_options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        options: dict[str, Any] = {**kwargs}
        if self._num_ctx is not None:
            options["num_ctx"] = self._num_ctx
        return options

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call ollama.Client.chat and return the response content string."""
        client = ollama.Client(host=self._base_url)
        options = self._build_options(kwargs)
        response = client.chat(
            model=self._model,
            messages=messages,
            options=options,
        )
        msg = response.message if hasattr(response, "message") else response["message"]
        content = msg.content if hasattr(msg, "content") else msg["content"]
        return content or ""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Delegate to chat() with a single user message."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream the Ollama chat response as text chunks."""
        async_client = ollama.AsyncClient(host=self._base_url)
        options = self._build_options(kwargs)
        try:
            response = await async_client.chat(
                model=self._model,
                messages=messages,
                stream=True,
                options=options,
            )
            async for chunk in response:
                msg = chunk.message if hasattr(chunk, "message") else chunk["message"]
                content = msg.content if hasattr(msg, "content") else msg["content"]
                if content:
                    yield content
        except Exception as exc:
            raise LLMAdapterError(str(exc)) from exc
