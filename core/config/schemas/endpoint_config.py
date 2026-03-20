"""EndpointConfig schema."""

from pydantic import BaseModel, Field


class EndpointConfig(BaseModel):
    """API endpoint configuration for a repository."""

    format_version: str = Field(default="1.0")
    repo_name: str
    api_type: str = Field(default="rest", description="API type: rest or graphql")
    endpoints: dict[str, list[str]] = Field(
        default_factory=dict, description="HTTP methods mapped to endpoint paths"
    )
