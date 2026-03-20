"""OllamaEmbeddingConfig schema."""

from pydantic import BaseModel, field_validator


class OllamaEmbeddingConfig(BaseModel):
    """Ollama embedding model configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text:latest"
    timeout_seconds: int = 60

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Ollama URL must start with http:// or https://")
        return v.rstrip("/")
