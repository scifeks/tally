"""Burp Suite connection configuration."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BurpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str = Field(
        default="http://localhost:1337",
        description="Burp REST API base URL",
    )
    api_key: str = Field(
        default="",
        description="Optional Burp REST API key",
    )
    mcp_url: str = Field(
        default="",
        description=(
            "SSE endpoint URL for Burp's MCP server (e.g. http://127.0.0.1:9876/sse)"
        ),
    )
    poll_interval_seconds: int = Field(
        default=30,
        ge=5,
        description="Seconds between Organizer poll cycles",
    )

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")
