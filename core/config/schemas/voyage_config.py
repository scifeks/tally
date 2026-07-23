"""VoyageConfig schema."""

from pydantic import BaseModel


class VoyageConfig(BaseModel):
    """Voyage AI embedding API configuration."""

    api_key: str = ""
    model: str
    timeout_seconds: int = 60
