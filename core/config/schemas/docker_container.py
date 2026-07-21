"""DockerContainer schema."""

from pydantic import BaseModel, Field, field_validator

from .validation import has_shell_metacharacters


class DockerContainer(BaseModel):
    """Docker container configuration for a tool."""

    name: str = Field(..., description="Docker container name")
    tool_path: str = Field(
        ...,
        description="Path to tool binary inside container",
    )

    @field_validator("name")
    @classmethod
    def name_no_metachar(cls, v: str) -> str:
        if has_shell_metacharacters(v):
            raise ValueError("container name contains a shell metacharacter")
        return v

    @field_validator("tool_path")
    @classmethod
    def tool_path_no_metachar(cls, v: str) -> str:
        if has_shell_metacharacters(v):
            raise ValueError("tool_path contains a shell metacharacter")
        return v
