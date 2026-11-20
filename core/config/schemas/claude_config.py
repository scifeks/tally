"""ClaudeConfig schema."""

import os
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class ClaudeConfig(BaseModel):
    """Anthropic Claude API configuration."""

    api_key: str = ""
    model: str = "claude-opus-4-6[1m]"
    max_tokens: int = 1024
    timeout_seconds: int = 60
    default_billing_method: Literal["plan", "api"] | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_env_var_fallback(cls, data: dict) -> dict:
        # Env var only applies when the config did not set a value.
        if isinstance(data, dict) and data.get("default_billing_method") is None:
            env_value = os.environ.get("ANTHROPIC_DEFAULT_BILLING_METHOD")
            if env_value:
                data["default_billing_method"] = env_value
        return data

    @field_validator("default_billing_method", mode="before")
    @classmethod
    def _normalize_billing_method(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, str):
            normalized = v.lower()
            if normalized not in ("plan", "api"):
                raise ValueError(
                    f"default_billing_method must be 'plan' or 'api', got {v!r}"
                )
            return normalized
        return v
