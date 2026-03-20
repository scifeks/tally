"""OllamaConfig schema."""

from pydantic import BaseModel, field_validator


class OllamaConfig(BaseModel):
    """Ollama connection and model configuration."""

    base_url: str = "http://localhost:11434"
    model: str
    timeout_seconds: int = 60

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL format is valid."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Ollama URL must start with http:// or https://")
        return v.rstrip("/")
