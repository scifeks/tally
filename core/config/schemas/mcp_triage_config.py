"""MCP triage orchestration configuration."""

from pydantic import BaseModel, ConfigDict, Field


class McpTriageConfig(BaseModel):
    """Settings for MCP triage agent dispatch."""

    model_config = ConfigDict(extra="ignore")

    max_concurrent_agents: int = Field(
        default=3,
        ge=1,
        le=10,
    )
