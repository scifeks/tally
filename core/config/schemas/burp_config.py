"""Burp Suite REST API connection configuration."""

from pydantic import BaseModel, field_validator


class BurpConfig(BaseModel):
    """Connection profile for a Burp Suite instance."""

    base_url: str = "http://localhost:1337"
    api_key: str = ""

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")
