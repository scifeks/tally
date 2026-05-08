"""OpenCodeConfig schema."""

from pydantic import BaseModel


class OpenCodeConfig(BaseModel):
    """LLM provider configuration for OpenCode triage agent."""

    api_key: str = ""
    api_provider: str = ""
