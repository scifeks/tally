"""Burp Suite connection configuration."""

from pydantic import BaseModel, ConfigDict, Field


class BurpConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
