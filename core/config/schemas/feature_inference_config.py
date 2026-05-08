"""FeatureInferenceConfig schema."""

from pydantic import BaseModel, field_validator


class FeatureInferenceConfig(BaseModel):
    """References a provider config with optional overrides."""

    provider: str
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("timeout_seconds", "num_ctx", "max_tokens")
    @classmethod
    def validate_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("Must be positive")
        return v
