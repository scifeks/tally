"""OpenAIConfig schema."""

from pydantic import BaseModel


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""

    api_key: str = ""
    model: str
    max_tokens: int = 4096
    timeout_seconds: int = 60
