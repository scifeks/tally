"""MCP server configuration."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class McpConfig(BaseModel):
    """MCP server bind address and port."""

    model_config = ConfigDict(extra="ignore")

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8765)

    @field_validator("host", mode="before")
    @classmethod
    def _strip_protocol(cls, v: str) -> str:
        if isinstance(v, str):
            for prefix in ("https://", "http://"):
                if v.startswith(prefix):
                    return v[len(prefix) :]
        return v
