"""LocalInferenceConfig schema."""

from pydantic import BaseModel, field_validator


class LocalInferenceConfig(BaseModel):
    """Local inference server configuration."""

    base_url: str = "http://localhost:11434"
    model: str
    timeout_seconds: int = 60
    num_ctx: int | None = None

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")
