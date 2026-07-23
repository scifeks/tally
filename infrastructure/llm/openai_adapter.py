"""OpenAI LLM provider adapter."""

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import openai

from application.ports.llm_provider import LLMAdapterError, LLMProvider

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMProvider):
    """LLMProvider backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout_seconds: int = 60,
    ) -> None:
        self._resolved_key = os.environ.get("OPENAI_API_KEY") or api_key or ""
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._client = openai.OpenAI(
            api_key=self._resolved_key or None,
            timeout=float(timeout_seconds),
        )

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        """Return True if an API key is configured."""
        return bool(self._resolved_key)

    def _normalise_kwargs(self, kwargs: dict[str, Any]) -> tuple[int, str]:
        """Pop and resolve max_tokens and model from kwargs."""
        num_predict = kwargs.pop("num_predict", None)
        max_tokens: int = (
            kwargs.pop("max_tokens", None)
            or (num_predict if num_predict else None)
            or self._max_tokens
        )
        model: str = kwargs.pop("model", self._model)
        return max_tokens, model

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call the OpenAI Chat Completions API and return the text response."""
        max_tokens, model = self._normalise_kwargs(kwargs)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            **kwargs,  # temperature, top_p, etc.
        }

        try:
            response = self._client.chat.completions.create(**create_kwargs)
        except openai.APIError as exc:
            raise LLMAdapterError(str(exc)) from exc

        logger.debug(
            "OpenAI response: model=%s prompt_tokens=%d completion_tokens=%d",
            response.model,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        return response.choices[0].message.content

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Delegate to chat() with a single user message."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream the OpenAI Chat Completions API response as text chunks."""
        max_tokens, model = self._normalise_kwargs(kwargs)

        stream_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }

        async_client = openai.AsyncOpenAI(
            api_key=self._resolved_key or None,
            timeout=float(self._timeout_seconds),
        )
        try:
            stream = await async_client.chat.completions.create(**stream_kwargs)
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except openai.APIError as exc:
            raise LLMAdapterError(str(exc)) from exc
