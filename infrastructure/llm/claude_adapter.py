"""Anthropic Claude LLM provider adapter."""

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from application.ports.llm_provider import LLMAdapterError, LLMProvider

logger = logging.getLogger(__name__)


class ClaudeAdapter(LLMProvider):
    """LLMProvider backed by the Anthropic Messages API.

    API key is resolved first from ANTHROPIC_API_KEY environment variable,
    then from config (global.json claude.api_key). The synchronous SDK client
    is instantiated once in __init__ and reused for chat()/complete() calls.
    The async client used by stream_chat() is created per call; streaming
    sessions are short-lived and the connection-pool overhead is small.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout_seconds: int = 60,
    ) -> None:
        self._resolved_key = os.environ.get("ANTHROPIC_API_KEY") or api_key or ""
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        self._client = anthropic.Anthropic(
            api_key=self._resolved_key or None,
            timeout=float(timeout_seconds),
        )

    @property
    def model(self) -> str:
        return self._model

    def is_available(self) -> bool:
        """Return True if an API key is configured.

        Returns False when api_key (config) is empty AND the ANTHROPIC_API_KEY
        environment variable is unset. Authentication errors still surface as
        LLMAdapterError from chat()/complete() even when this returns True.
        """
        return bool(self._resolved_key)

    def _normalise_kwargs(self, kwargs: dict[str, Any]) -> tuple[int, str]:
        """Pop and resolve max_tokens and model from kwargs.

        Mutates ``kwargs`` (consumes ``num_predict``, ``max_tokens``,
        ``model``). Remaining kwargs are forwarded to the SDK as-is
        (e.g. ``temperature``, ``top_p``).
        """
        num_predict = kwargs.pop("num_predict", None)
        max_tokens: int = (
            kwargs.pop("max_tokens", None)
            or (num_predict if num_predict else None)
            or self._max_tokens
        )
        model: str = kwargs.pop("model", self._model)
        return max_tokens, model

    def _split_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], str | None]:
        """Extract system messages and validate roles.

        Anthropic's Messages API requires the system prompt as a top-level
        ``system`` parameter and rejects any role other than ``user`` /
        ``assistant`` in the messages list.
        """
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        api_messages = [m for m in messages if m.get("role") != "system"]

        if not api_messages:
            raise LLMAdapterError(
                "messages must contain at least one non-system message"
            )

        invalid_roles = {
            m["role"]
            for m in api_messages
            if m.get("role") not in ("user", "assistant")
        }
        if invalid_roles:
            raise LLMAdapterError(
                f"Invalid message role(s) for Anthropic API: "
                f"{sorted(invalid_roles)}. "
                "Only 'user' and 'assistant' are accepted."
            )

        system = "\n\n".join(system_parts) if system_parts else None
        return api_messages, system

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call the Anthropic Messages API and return the text response.

        Raises:
            LLMAdapterError: For empty/invalid messages, or any SDK error.
        """
        max_tokens, model = self._normalise_kwargs(kwargs)
        api_messages, system = self._split_messages(messages)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            **kwargs,  # temperature, top_p, etc.
        }
        if system is not None:
            create_kwargs["system"] = system

        try:
            response = self._client.messages.create(**create_kwargs)
        except anthropic.APIError as exc:
            raise LLMAdapterError(str(exc)) from exc

        logger.debug(
            "Claude response: model=%s input_tokens=%d output_tokens=%d",
            response.model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return response.content[0].text

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Delegate to chat() with a single user message."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream the Anthropic Messages API response as text chunks.

        Yields each fragment from ``stream.text_stream`` verbatim.
        Cancellation propagates through ``aclose()`` on the generator,
        which closes the ``async with`` block and releases the underlying
        HTTP stream.

        Raises:
            LLMAdapterError: For empty/invalid messages, or any SDK error
                (raised before the first yield, or during iteration).
        """
        max_tokens, model = self._normalise_kwargs(kwargs)
        api_messages, system = self._split_messages(messages)

        stream_kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if system is not None:
            stream_kwargs["system"] = system

        async_client = anthropic.AsyncAnthropic(
            api_key=self._resolved_key or None,
            timeout=float(self._timeout_seconds),
        )
        try:
            async with async_client.messages.stream(**stream_kwargs) as stream:
                async for chunk in stream.text_stream:
                    yield chunk
        except anthropic.APIError as exc:
            raise LLMAdapterError(str(exc)) from exc
