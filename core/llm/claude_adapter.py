"""Anthropic Claude LLM provider adapter."""

import logging
import os
from typing import Any

import anthropic

from .base import LLMAdapterError, LLMProvider

logger = logging.getLogger(__name__)


class ClaudeAdapter(LLMProvider):
    """LLMProvider backed by the Anthropic Messages API.

    API key resolution order:
      1. ANTHROPIC_API_KEY environment variable (takes precedence).
      2. api_key from config (global.json claude.api_key).

    The SDK client is instantiated once in __init__ and reused for all calls.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout_seconds: int = 60,
    ) -> None:
        # Resolve key at construction time; stored for is_available() check.
        self._resolved_key = os.environ.get("ANTHROPIC_API_KEY") or api_key or ""
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=self._resolved_key or None,
            timeout=float(timeout_seconds),
        )

    def is_available(self) -> bool:
        """Return True if an API key is configured.

        Returns False when api_key (config) is empty AND the ANTHROPIC_API_KEY
        environment variable is unset. Authentication errors still surface as
        LLMAdapterError from chat()/complete() even when this returns True.
        """
        return bool(self._resolved_key)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Call the Anthropic Messages API and return the text response.

        Handles two adapter responsibilities:
        - Extracts {"role": "system"} messages and passes them as the
          top-level `system` parameter (required by the Anthropic API).
        - Pops the Ollama-specific `num_predict` kwarg and uses it as a
          max_tokens hint so callers work regardless of which adapter is active.

        Raises:
            LLMAdapterError: For empty/invalid messages, or any SDK error.
        """
        # --- kwarg normalisation ---
        num_predict = kwargs.pop("num_predict", None)
        max_tokens: int = (
            kwargs.pop("max_tokens", None)
            or (num_predict if num_predict else None)
            or self._max_tokens
        )
        model: str = kwargs.pop("model", self._model)

        # --- message extraction ---
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
                f"Invalid message role(s) for Anthropic API: {sorted(invalid_roles)}. "
                "Only 'user' and 'assistant' are accepted."
            )

        # --- API call ---
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            **kwargs,  # temperature, top_p, etc.
        }
        if system_parts:
            create_kwargs["system"] = "\n\n".join(system_parts)

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
