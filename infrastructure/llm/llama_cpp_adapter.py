"""llama.cpp LLM provider adapter."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any, cast

import openai

from application.ports.llm_provider import LLMAdapterError, LLMProvider

logger = logging.getLogger(__name__)


class LlamaCppAdapter(LLMProvider):
    """LLMProvider backed by a local llama.cpp HTTP server."""

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
        try:
            with urllib.request.urlopen(f"{self._base_url}/health", timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    def _normalise_kwargs(self, kwargs: dict[str, Any]) -> None:
        """Map Ollama-specific kwargs to OpenAI equivalents."""
        num_predict = kwargs.pop("num_predict", None)
        if num_predict and "max_tokens" not in kwargs:
            kwargs["max_tokens"] = num_predict
        kwargs.pop("num_ctx", None)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self._normalise_kwargs(kwargs)
        try:
            client = openai.OpenAI(
                base_url=f"{self._base_url}/v1",
                api_key="not-needed",
                timeout=self._timeout,
            )
            response = client.chat.completions.create(
                model=self._model,
                messages=cast(Any, messages),
                **kwargs,
            )
            content = response.choices[0].message.content
            return content or ""
        except Exception as exc:
            raise LLMAdapterError(str(exc)) from exc

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        self._normalise_kwargs(kwargs)
        try:
            async_client = openai.AsyncOpenAI(
                base_url=f"{self._base_url}/v1",
                api_key="not-needed",
                timeout=self._timeout,
            )
            response = await async_client.chat.completions.create(
                model=self._model,
                messages=cast(Any, messages),
                stream=True,
                **kwargs,
            )
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as exc:
            raise LLMAdapterError(str(exc)) from exc
