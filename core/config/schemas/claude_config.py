"""ClaudeConfig schema."""

from pydantic import BaseModel


class ClaudeConfig(BaseModel):
    """Anthropic Claude API configuration."""

    api_key: str = ""
    model: str = "claude-opus-4-6[1m]"
    max_tokens: int = 1024
    timeout_seconds: int = 60
