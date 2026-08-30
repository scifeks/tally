"""MCP server configuration."""

from pydantic import BaseModel, ConfigDict, Field


class McpConfig(BaseModel):
    """MCP server host and port for .mcp.json generation."""

    model_config = ConfigDict(extra="ignore")

    host: str = Field(default="http://127.0.0.1")
    port: int = Field(default=8765)
