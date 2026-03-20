"""DockerContainer schema."""

from pydantic import BaseModel, Field


class DockerContainer(BaseModel):
    """Docker container configuration for a tool."""

    name: str = Field(..., description="Docker container name")
    tool_path: str = Field(..., description="Path to tool binary inside container")
